import requests

url = "https://mis.taifex.com.tw/futures/api/getQuoteList"
payload = {
    "MarketType": "1",  # 夜盤
    "SymbolType": "F",
    "KindID": "1",
    "CID": "TXF",
    "ExpireMonth": "",
    "RowSize": "全部",
    "PageNo": "",
    "SortColumn": "",
    "AscDesc": "A"
}

r = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
print(f"HTTP Status: {r.status_code}")
data = r.json()
quotes = data.get("RtData", {}).get("QuoteList", [])
print(f"合約數量: {len(quotes)}")

for q in quotes[:3]:
    print(f"{q['SymbolID']}: {q.get('CLastPrice', 'N/A')}")
