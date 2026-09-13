import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv('.env')

token = os.getenv('NOTION_API_KEY')
print("Checking token present:", bool(token))

notion = Client(auth=token)

try:
    res = notion.search()
    items = res.get('results', [])
    print(f"\nTotal connected items found: {len(items)}\n")
    for item in items:
        obj_type = item.get('object', 'unknown')
        item_id = item.get('id', '').replace('-', '')

        title = 'Untitled'
        if 'title' in item and isinstance(item['title'], list) and item['title']:
            title = item['title'][0].get('plain_text', 'Untitled')
        elif 'properties' in item and isinstance(item['properties'], dict):
            for p_name, p_val in item['properties'].items():
                if isinstance(p_val, dict) and p_val.get('type') == 'title' and p_val.get('title'):
                    title = p_val['title'][0].get('plain_text', 'Untitled')
                    break

        print(f"• [{obj_type.upper()}] '{title}'")
        print(f"  ID: {item_id}")
        if 'properties' in item and isinstance(item['properties'], dict):
            print(f"  Columns: {list(item['properties'].keys())}")
        print("-" * 40)
except Exception as e:
    print("Search error:", e)