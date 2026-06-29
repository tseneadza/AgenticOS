import React from "react";
import ReactDOM from "react-dom/client";
import "./theme.css";          // FR-60: token contract — load before App's styles
import App from "./App";
import Hud from "./Hud";        // FR-63: compact always-on-top HUD (#/hud route)

// Single bundle, two entry points: the second WebviewWindow loads index.html#/hud.
const isHud = window.location.hash.startsWith("#/hud");

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {isHud ? <Hud /> : <App />}
  </React.StrictMode>,
);
