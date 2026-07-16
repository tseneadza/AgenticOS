"""Phase 16a tests — Brain Scanner vault API (read-only slice).

Covers gui/sidecar/routes/api_vault.py per docs/PHASE16_BRAIN_SCANNER.md §5:

- /api/vault/tree  — shape, ordering, exclusion of .obsidian/, dotfiles, non-.md
- /api/vault/note  — content/mtime/size; 404 missing; 400 non-.md; 400 ``..``
  escape; 400 absolute-outside; 400 symlink-inside-vault-pointing-outside
  (Phase 15b resolve-then-check scoping, see GLOSSARY "Allowed roots")
- /api/vault/graph — note + tag nodes, wikilink edges (#heading / |alias forms),
  Obsidian shortest-path duplicate-basename rule, unresolved + self links
  dropped, parse hygiene (frontmatter tags list AND comma-string, fenced/inline
  code stripped), tags as NODES with note→tag edges — never pairwise cliques
- cache — (count, max-mtime) scan key: mtime bump → fresh graph; unchanged key
  → stale-by-design until ``?refresh=1`` forces a rebuild
- empty / missing vault → 503 on all three routes

Hermetic per the HIGH review requirement: every test injects a tmp_path vault
via the documented seam ``api_vault.set_vault_root()`` (autouse fixture, reset
to None on teardown) — the real ~/Brain2 is NEVER read.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from gui.sidecar.routes import api_vault


# ═══════════════════════════════════════════════════════════════════════════════
# Fixture vault
# ═══════════════════════════════════════════════════════════════════════════════

ALPHA = """\
---
tags:
  - shared
  - "#alpha-extra"
---
Links: [[Beta]], heading form [[Nested Note#Some Heading]], alias form
[[Dup|see the dup note]].

Self link [[Alpha]] must be dropped; unresolved [[Ghost Note]] is dropped too.

Body tag #bodytag is real. Numeric refs like issue #42 and glued css
color:#fff are not tags. Bare hex swatches #fff and #d97b4f appear here for
the hex-false-positive check.
"""

BETA = """\
---
tags: shared, beta-thing
---
Beta has NO live links or body tags — everything below is code and must be
stripped before parsing (design §5 parse hygiene).

```python
graph = load("[[Alpha]]")  # a wikilink in a fence — not an edge
mark = "#codetag"          # a tag in a fence — not a tag
```

Inline code too: `[[Gamma]] #inlinetag` stays inert.
"""

GAMMA = """\
Gamma has no frontmatter. Body mentions #shared so three notes share that tag.
"""

NESTED = """\
# Some Heading

Nested links back to [[Alpha]].
"""

DELTA = """\
Deep note linking [[Nested Note]] by basename.
"""


def _build_vault(root: Path) -> None:
    """A small but adversarial vault exercising every §5 parse/scope rule."""
    (root / "Sub" / "Deep").mkdir(parents=True)
    # Excluded from tree/graph: .obsidian/, dotfiles, dot-dirs, non-.md assets.
    (root / ".obsidian").mkdir()
    (root / ".obsidian" / "workspace.json").write_text("{}")
    (root / ".obsidian" / "plugin-note.md").write_text("# hidden md")
    (root / ".hidden.md").write_text("dotfile note")
    (root / ".trash").mkdir()
    (root / ".trash" / "gone.md").write_text("deleted")
    (root / "image.png").write_bytes(b"\x89PNG not markdown")
    # Notes.
    (root / "Alpha.md").write_text(ALPHA)
    (root / "Beta.md").write_text(BETA)
    (root / "Gamma.md").write_text(GAMMA)
    (root / "Dup.md").write_text("Root dup — shortest path, should win.")
    (root / "Sub" / "Dup.md").write_text("Sub dup — longer path, must lose.")
    (root / "Sub" / "Nested Note.md").write_text(NESTED)
    (root / "Sub" / "Deep" / "Delta.md").write_text(DELTA)


NOTE_IDS = {
    "Alpha.md", "Beta.md", "Gamma.md", "Dup.md",
    "Sub/Dup.md", "Sub/Nested Note.md", "Sub/Deep/Delta.md",
}


@pytest.fixture(autouse=True)
def vault(tmp_path):
    """Inject a tmp_path vault via the documented test seam; ALWAYS reset.

    Autouse so no test in this file can ever fall through to the config
    default and touch the real ~/Brain2 (HIGH review requirement). The seam
    also invalidates the module-global graph cache on both set and reset,
    which keeps tests isolated from each other.
    """
    root = tmp_path / "vault"
    _build_vault(root)
    api_vault.set_vault_root(root)
    yield root
    api_vault.set_vault_root(None)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from gui.sidecar.app import app as fastapi_app
    return TestClient(fastapi_app)


def _graph(client, **params):
    r = client.get("/api/vault/graph", params=params)
    assert r.status_code == 200
    return r.json()


def _link_edges(graph) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in graph["edges"] if e["kind"] == "link"}


def _tag_edges(graph) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in graph["edges"] if e["kind"] == "tag"}


# ═══════════════════════════════════════════════════════════════════════════════
# /api/vault/tree — shape + hygiene
# ═══════════════════════════════════════════════════════════════════════════════

class TestTree:
    def test_shape_and_ordering(self, client, vault):
        body = client.get("/api/vault/tree").json()
        assert body["root"] == str(vault.resolve())
        top = body["tree"]
        # Dirs sort before files; files case-insensitively by name.
        assert [e["name"] for e in top] == [
            "Sub", "Alpha.md", "Beta.md", "Dup.md", "Gamma.md",
        ]
        sub = next(e for e in top if e["name"] == "Sub")
        assert sub["type"] == "dir"
        assert [e["name"] for e in sub["children"]] == [
            "Deep", "Dup.md", "Nested Note.md",
        ]
        deep = sub["children"][0]
        assert [e["name"] for e in deep["children"]] == ["Delta.md"]
        # Paths are vault-relative.
        assert deep["children"][0]["path"] == "Sub/Deep/Delta.md"
        nested = next(e for e in sub["children"] if e["name"] == "Nested Note.md")
        assert nested == {
            "name": "Nested Note.md", "path": "Sub/Nested Note.md", "type": "file",
        }

    def test_excludes_dotfiles_and_non_md(self, client):
        body = client.get("/api/vault/tree").json()

        def flatten(entries):
            for e in entries:
                yield e["path"]
                yield from flatten(e.get("children", []))

        paths = list(flatten(body["tree"]))
        assert not any(".obsidian" in p for p in paths)
        assert not any(".trash" in p for p in paths)
        assert ".hidden.md" not in paths
        assert "image.png" not in paths
        assert set(paths) == NOTE_IDS | {"Sub", "Sub/Deep"}


# ═══════════════════════════════════════════════════════════════════════════════
# /api/vault/note — read + Phase 15b-style scoping
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoteRead:
    def test_read_content_mtime_size(self, client, vault):
        r = client.get("/api/vault/note", params={"path": "Alpha.md"})
        assert r.status_code == 200
        body = r.json()
        assert body["path"] == "Alpha.md"
        assert body["content"] == ALPHA
        stat = (vault / "Alpha.md").stat()
        assert body["mtime"] == pytest.approx(stat.st_mtime)
        assert body["size"] == stat.st_size == len(ALPHA.encode())

    def test_read_nested_path_with_space(self, client):
        r = client.get("/api/vault/note", params={"path": "Sub/Nested Note.md"})
        assert r.status_code == 200
        assert r.json()["path"] == "Sub/Nested Note.md"
        assert "[[Alpha]]" in r.json()["content"]

    def test_missing_note_404(self, client):
        r = client.get("/api/vault/note", params={"path": "Nope.md"})
        assert r.status_code == 404

    def test_non_md_400(self, client):
        # image.png exists and is inside the vault — still refused (.md only).
        r = client.get("/api/vault/note", params={"path": "image.png"})
        assert r.status_code == 400

    def test_empty_path_400_and_missing_param_422(self, client):
        assert client.get("/api/vault/note", params={"path": "  "}).status_code == 400
        assert client.get("/api/vault/note").status_code == 422

    def test_dotdot_escape_400(self, client, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.md").write_text("outside the vault")
        r = client.get("/api/vault/note", params={"path": "../outside/secret.md"})
        assert r.status_code == 400
        # Even a nonexistent ``..`` target is scope-rejected (400), never 404 —
        # scoping is checked before existence so probing can't map the disk.
        r = client.get("/api/vault/note", params={"path": "../nowhere.md"})
        assert r.status_code == 400

    def test_absolute_path_outside_root_400(self, client, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        target = outside / "secret.md"
        target.write_text("outside the vault")
        r = client.get("/api/vault/note", params={"path": str(target)})
        assert r.status_code == 400

    def test_symlink_escape_rejected(self, client, vault, tmp_path):
        # A symlink INSIDE the vault pointing outside resolves outside and is
        # rejected (GLOSSARY "Allowed roots": symlink-resolved before check).
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.md"
        secret.write_text("must never be served")
        (vault / "Escape.md").symlink_to(secret)
        r = client.get("/api/vault/note", params={"path": "Escape.md"})
        assert r.status_code == 400
        assert "must never be served" not in r.text

    def test_inside_root_paths_resolve_ok(self, client, vault):
        # Resolve-then-check, not string matching: an absolute path inside the
        # root and a ``..`` hop that STAYS inside both serve normally.
        r = client.get("/api/vault/note", params={"path": str(vault / "Alpha.md")})
        assert r.status_code == 200
        r = client.get("/api/vault/note", params={"path": "Sub/../Alpha.md"})
        assert r.status_code == 200
        assert r.json()["path"] == "Alpha.md"


# ═══════════════════════════════════════════════════════════════════════════════
# /api/vault/graph — nodes, edges, parse hygiene
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraph:
    def test_note_nodes(self, client):
        g = _graph(client)
        notes = {n["id"]: n for n in g["nodes"] if n["type"] == "note"}
        assert set(notes) == NOTE_IDS
        assert notes["Alpha.md"]["label"] == "Alpha"
        assert notes["Alpha.md"]["folder"] == ""          # root-level note
        assert notes["Sub/Nested Note.md"]["folder"] == "Sub"
        assert notes["Sub/Deep/Delta.md"]["folder"] == "Sub"  # TOP-level folder
        # Excluded sources never become nodes.
        assert not any(".obsidian" in i or ".hidden" in i or ".trash" in i
                       for i in notes)

    def test_wikilink_edges_heading_and_alias_forms(self, client):
        links = _link_edges(_graph(client))
        assert ("Alpha.md", "Beta.md") in links                   # plain
        assert ("Alpha.md", "Sub/Nested Note.md") in links        # [[X#Heading]]
        assert ("Alpha.md", "Dup.md") in links                    # [[X|alias]]
        assert ("Sub/Nested Note.md", "Alpha.md") in links        # backlink
        assert ("Sub/Deep/Delta.md", "Sub/Nested Note.md") in links

    def test_duplicate_basename_shortest_path_wins(self, client):
        # Two Dup.md exist; Obsidian's rule picks the shortest relative path.
        links = _link_edges(_graph(client))
        assert ("Alpha.md", "Dup.md") in links
        assert ("Alpha.md", "Sub/Dup.md") not in links

    def test_unresolved_and_self_links_dropped(self, client):
        g = _graph(client)
        assert not any("Ghost" in n["id"] for n in g["nodes"])
        links = _link_edges(g)
        assert not any("Ghost" in s or "Ghost" in t for s, t in links)
        assert ("Alpha.md", "Alpha.md") not in links

    def test_code_blocks_and_inline_code_are_inert(self, client):
        # Every link/tag in Beta lives in a fence or inline code → no edges,
        # and #codetag / #inlinetag never become tag nodes.
        g = _graph(client)
        assert not any(s == "Beta.md" for s, _ in _link_edges(g))
        tag_ids = {n["id"] for n in g["nodes"] if n["type"] == "tag"}
        assert "#codetag" not in tag_ids
        assert "#inlinetag" not in tag_ids

    def test_frontmatter_and_body_tags_become_nodes(self, client):
        g = _graph(client)
        tags = {n["id"]: n for n in g["nodes"] if n["type"] == "tag"}
        assert "#shared" in tags          # frontmatter list + string + body
        assert "#alpha-extra" in tags     # list form, leading '#' stripped
        assert "#beta-thing" in tags      # comma-string form
        assert "#bodytag" in tags         # body form
        assert tags["#shared"]["folder"] == "#tags"
        assert "#42" not in tags          # numeric ref rejected (leading letter)
        # Frontmatter comma-string parsing: Beta's tags reach the graph even
        # though Beta's body contributes nothing.
        tag_edges = _tag_edges(g)
        assert ("Beta.md", "#beta-thing") in tag_edges

    def test_shared_tag_is_a_node_not_a_clique(self, client):
        # THE anti-clique requirement (design §5 MEDIUM): #shared sits on
        # exactly 3 notes → exactly 3 note→tag edges and ZERO note-note edges
        # introduced by the tag.
        g = _graph(client)
        shared_edges = {(s, t) for s, t in _tag_edges(g) if t == "#shared"}
        assert shared_edges == {
            ("Alpha.md", "#shared"),
            ("Beta.md", "#shared"),
            ("Gamma.md", "#shared"),
        }
        # The only note-note edge among the trio is Alpha's explicit wikilink.
        trio = {"Alpha.md", "Beta.md", "Gamma.md"}
        trio_links = {(s, t) for s, t in _link_edges(g) if s in trio and t in trio}
        assert trio_links == {("Alpha.md", "Beta.md")}
        # Edge kinds partition cleanly: tag edges end at tag nodes only,
        # link edges never do.
        assert all(t.startswith("#") for _, t in _tag_edges(g))
        assert not any(t.startswith("#") for _, t in _link_edges(g))

    def test_bare_hex_colors_are_not_tags(self, client):
        # HEX_COLOR_RE post-filter: letter-leading pure-hex candidates at CSS
        # color lengths (#fff, #d97b4f) are colors, not tags (body-only rule).
        tag_ids = {n["id"] for n in _graph(client)["nodes"] if n["type"] == "tag"}
        assert "#fff" not in tag_ids
        assert "#d97b4f" not in tag_ids


# ═══════════════════════════════════════════════════════════════════════════════
# Graph cache — (count, max-mtime) key + ?refresh=1
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraphCache:
    def test_mtime_change_invalidates(self, client, vault):
        g0 = _graph(client)
        assert ("Gamma.md", "Alpha.md") not in _link_edges(g0)
        # Any writer (real Obsidian, process-raw-notes, fs_mcp) bumps mtime —
        # the scan key changes and the next GET rebuilds without ?refresh.
        gamma = vault / "Gamma.md"
        gamma.write_text(GAMMA + "\nNow links [[Alpha]].\n")
        st = gamma.stat()
        os.utime(gamma, (st.st_atime, st.st_mtime + 10))  # defeat mtime granularity
        g1 = _graph(client)
        assert ("Gamma.md", "Alpha.md") in _link_edges(g1)

    def test_unchanged_key_serves_cache_and_refresh_rebuilds(self, client, vault):
        g0 = _graph(client)
        assert ("Gamma.md", "Beta.md") not in _link_edges(g0)
        # Mutate content but restore the original mtime: (count, max-mtime) is
        # unchanged, so the cheap scan CANNOT see the write → stale cache is
        # served (documented §5 tradeoff) until ?refresh=1 forces the rebuild.
        gamma = vault / "Gamma.md"
        st = gamma.stat()
        gamma.write_text(GAMMA + "\nNow links [[Beta]].\n")
        os.utime(gamma, (st.st_atime, st.st_mtime))
        g1 = _graph(client)
        assert ("Gamma.md", "Beta.md") not in _link_edges(g1)  # stale, by design
        g2 = _graph(client, refresh=1)
        assert ("Gamma.md", "Beta.md") in _link_edges(g2)
        # And the forced rebuild replaces the cache for subsequent plain GETs.
        g3 = _graph(client)
        assert ("Gamma.md", "Beta.md") in _link_edges(g3)


# ═══════════════════════════════════════════════════════════════════════════════
# Missing / empty vault → clean 503 (design §5: in 16a, not deferred to polish)
# ═══════════════════════════════════════════════════════════════════════════════

class TestVaultMissing:
    ROUTES = ("/api/vault/tree", "/api/vault/graph")

    def _assert_all_503(self, client):
        for route in self.ROUTES:
            assert client.get(route).status_code == 503, route
        r = client.get("/api/vault/note", params={"path": "Alpha.md"})
        assert r.status_code == 503

    def test_missing_root_503(self, client, tmp_path):
        api_vault.set_vault_root(tmp_path / "does-not-exist")
        self._assert_all_503(client)

    def test_empty_dir_503(self, client, tmp_path):
        empty = tmp_path / "empty-vault"
        empty.mkdir()
        api_vault.set_vault_root(empty)
        self._assert_all_503(client)

    def test_no_md_files_503(self, client, tmp_path):
        assets_only = tmp_path / "assets-only"
        assets_only.mkdir()
        (assets_only / "image.png").write_bytes(b"\x89PNG")
        (assets_only / "notes.txt").write_text("not markdown")
        api_vault.set_vault_root(assets_only)
        self._assert_all_503(client)
