#!/usr/bin/env python3
"""
Examples of using the Anthropic Usage Tool

Run these examples to see how to use the tool in your projects.
"""

from anthropic_usage import AnthropicUsageClient, format_as_table, format_as_json


def example_1_get_account_info():
    """Example 1: Get account information"""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Get Account Information")
    print("=" * 80)

    client = AnthropicUsageClient()
    account = client.get_account_info()

    if account.get("success"):
        print("\n✓ Account Info Retrieved:")
        print(format_as_json(account["data"], pretty=True))
    else:
        print(f"\n✗ Error: {account.get('error')}")


def example_2_get_usage_metrics():
    """Example 2: Get usage metrics"""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Get Usage Metrics")
    print("=" * 80)

    client = AnthropicUsageClient()
    usage = client.get_usage_metrics()

    if usage.get("success"):
        print("\n✓ Usage Metrics Retrieved:")
        print(format_as_json(usage["data"], pretty=True))
    else:
        print(f"\n✗ Error: {usage.get('error')}")


def example_3_get_all_data():
    """Example 3: Get all data in table format"""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Get All Data (Table Format)")
    print("=" * 80)

    client = AnthropicUsageClient()
    all_data = client.get_all_data()

    if all_data.get("success"):
        print("\n✓ Complete Data Retrieved:")
        print(format_as_table(all_data))
    else:
        print(f"\n✗ Error: {all_data.get('error')}")


def example_4_get_models():
    """Example 4: Get available models"""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Get Available Models")
    print("=" * 80)

    client = AnthropicUsageClient()
    models = client.get_models()

    if models.get("success"):
        print("\n✓ Models Retrieved:")
        if isinstance(models.get("data"), dict):
            model_list = models["data"].get("data", [])
            print(f"\nAvailable models ({len(model_list)}):")
            for model in model_list:
                if isinstance(model, dict):
                    model_id = model.get("id", "Unknown")
                    print(f"  • {model_id}")
        else:
            print(format_as_json(models["data"], pretty=True))
    else:
        print(f"\n✗ Error: {models.get('error')}")


def example_5_get_rate_limits():
    """Example 5: Get rate limit information"""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Get Rate Limits")
    print("=" * 80)

    client = AnthropicUsageClient()
    limits = client.get_rate_limits()

    if limits.get("success"):
        print("\n✓ Rate Limits Retrieved:")
        print(format_as_json(limits["data"], pretty=True))
    else:
        print(f"\n✗ Error: {limits.get('error')}")


def example_6_error_handling():
    """Example 6: Handling errors gracefully"""
    print("\n" + "=" * 80)
    print("EXAMPLE 6: Error Handling")
    print("=" * 80)

    # This example shows how to handle errors
    try:
        # Try with invalid API key (won't actually fail here, just shows pattern)
        client = AnthropicUsageClient()
        result = client.get_account_info()

        if result.get("success"):
            print("\n✓ Success!")
            print(result["data"])
        else:
            print(f"\n✗ API Error:")
            print(f"  Error: {result.get('error')}")
            if "details" in result:
                print(f"  Details: {result.get('details')}")

    except ValueError as e:
        print(f"\n✗ Configuration Error: {e}")
        print("  Make sure ANTHROPIC_API_KEY is set in .env.local")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("ANTHROPIC USAGE TOOL - EXAMPLES")
    print("=" * 80)
    print("\nThese examples show how to use the AnthropicUsageClient")
    print("in your own Python projects.")

    try:
        # Run examples (comment out any you want to skip)
        example_1_get_account_info()
        example_2_get_usage_metrics()
        example_3_get_all_data()
        example_4_get_models()
        example_5_get_rate_limits()
        example_6_error_handling()

        print("\n" + "=" * 80)
        print("ALL EXAMPLES COMPLETED")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback
        traceback.print_exc()
