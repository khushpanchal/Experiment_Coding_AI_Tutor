from mcp.server.fastmcp import FastMCP
import requests

mcp = FastMCP()


@mcp.tool(
    name="get_crypto_price",
    description="Fetch the current price of a cryptocurrency from CoinGecko."
)
def get_crypto_price(
    coin: str,
    currency: str = "usd"
) -> float:

    coin = coin.lower()
    currency = currency.lower()

    url = "https://api.coingecko.com/api/v3/simple/price"

    params = {
        "ids": coin,
        "vs_currencies": currency
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    if coin not in data or currency not in data[coin]:
        raise ValueError("Price data not found")

    return data[coin][currency]


if __name__ == "__main__":
    mcp.run(transport="sse")
