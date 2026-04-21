#!/usr/bin/env python3
"""
Data Extraction Skills - Demo Examples

Shows how to use pre-built data extraction agents
"""

import asyncio
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cluster.skills.data_extraction import (
    XMLExtractorAgent,
    JSONExtractorAgent,
    CSVExtractorAgent,
    ParquetExtractorAgent,
    XPathExtractorAgent
)


async def demo_xml_extraction():
    """Demo XML extraction"""
    print("\n=== XML Extraction Demo ===\n")

    # Create sample XML
    xml_content = """<?xml version="1.0"?>
    <catalog>
        <product id="1" category="electronics">
            <name>Laptop</name>
            <price>999.99</price>
            <stock>50</stock>
        </product>
        <product id="2" category="electronics">
            <name>Mouse</name>
            <price>29.99</price>
            <stock>200</stock>
        </product>
        <product id="3" category="books">
            <name>Python Guide</name>
            <price>49.99</price>
            <stock>30</stock>
        </product>
    </catalog>
    """

    agent = XMLExtractorAgent()

    # Extract electronics products
    electronics = await agent.extract(xml_content, {
        'xpath': '//product[@category="electronics"]',
        'output_format': 'dict'
    })

    print("Electronics products:")
    for product in electronics:
        print(f"  - {product}")

    # Extract all product names
    names = await agent.extract(xml_content, {
        'xpath': '//product/name/text()',
        'output_format': 'text'
    })

    print(f"\nProduct names: {names}")


async def demo_json_extraction():
    """Demo JSON extraction"""
    print("\n=== JSON Extraction Demo ===\n")

    # Create sample JSON
    json_content = """{
        "store": {
            "books": [
                {"title": "Python Basics", "price": 29.99, "in_stock": true},
                {"title": "Advanced AI", "price": 49.99, "in_stock": true},
                {"title": "Web Dev", "price": 39.99, "in_stock": false}
            ],
            "electronics": [
                {"name": "Laptop", "price": 999.99, "in_stock": true}
            ]
        }
    }"""

    agent = JSONExtractorAgent()

    # Extract book titles
    titles = await agent.extract(json_content, {
        'jsonpath': '$.store.books[*].title'
    })

    print(f"Book titles: {titles}")

    # Extract in-stock books
    in_stock_books = await agent.extract(json_content, {
        'jsonpath': '$.store.books[*]',
        'filter': lambda x: x['in_stock'] == True
    })

    print(f"\nIn-stock books: {in_stock_books}")

    # Flatten nested structure
    flat = await agent.extract(json_content, {
        'flatten': True
    })

    print(f"\nFlattened structure:")
    for key, value in flat.items():
        print(f"  {key}: {value}")


async def demo_csv_extraction():
    """Demo CSV extraction"""
    print("\n=== CSV Extraction Demo ===\n")

    # Create sample CSV
    csv_path = Path("/tmp/sample_sales.csv")
    csv_path.write_text("""date,region,product,amount,quantity
2024-01-01,North,Laptop,999.99,5
2024-01-01,South,Mouse,29.99,20
2024-01-02,North,Keyboard,79.99,10
2024-01-02,South,Laptop,999.99,3
2024-01-03,North,Mouse,29.99,50
""")

    agent = CSVExtractorAgent()

    # Extract specific columns
    data = await agent.extract_columns(str(csv_path), ['date', 'product', 'amount'])
    print(f"Sample data (first 2 rows):")
    for row in data[:2]:
        print(f"  {row}")

    # Filter high-value sales
    high_value = await agent.filter_rows(
        str(csv_path),
        lambda row: row['amount'] > 100
    )
    print(f"\nHigh-value sales: {len(high_value)} items")

    # Get column statistics
    stats = await agent.get_column_stats(str(csv_path), 'amount')
    print(f"\nAmount statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


async def demo_xpath_web():
    """Demo XPath for web scraping"""
    print("\n=== XPath Web Scraping Demo ===\n")

    # Create sample HTML
    html_content = """
    <html>
        <body>
            <h1>Products</h1>
            <div class="product">
                <h2 class="name">Laptop</h2>
                <span class="price">$999.99</span>
                <p class="description">High-performance laptop</p>
            </div>
            <div class="product">
                <h2 class="name">Mouse</h2>
                <span class="price">$29.99</span>
                <p class="description">Wireless mouse</p>
            </div>
        </body>
    </html>
    """

    agent = XPathExtractorAgent()

    # Extract product information
    products = await agent.extract_with_patterns(html_content, {
        'names': '//h2[@class="name"]/text()',
        'prices': '//span[@class="price"]/text()',
        'descriptions': '//p[@class="description"]/text()'
    })

    print("Extracted products:")
    for i in range(len(products['names'])):
        print(f"\n  Product {i+1}:")
        print(f"    Name: {products['names'][i]}")
        print(f"    Price: {products['prices'][i]}")
        print(f"    Description: {products['descriptions'][i]}")


async def demo_integration():
    """Demo integration of multiple extractors"""
    print("\n=== Multi-Format Integration Demo ===\n")

    # Simulate extracting from different formats and combining
    xml_agent = XMLExtractorAgent()
    json_agent = JSONExtractorAgent()

    xml_data = await xml_agent.extract("""<?xml version="1.0"?>
    <products>
        <product><name>Item A</name><price>100</price></product>
        <product><name>Item B</name><price>200</price></product>
    </products>
    """, {'output_format': 'dict'})

    json_data = await json_agent.extract("""{
        "products": [
            {"name": "Item C", "price": 300},
            {"name": "Item D", "price": 400}
        ]
    }""", {'jsonpath': '$.products[*]'})

    # Combine data from different sources
    all_products = []

    # Extract from XML
    if 'products' in xml_data:
        xml_products = xml_data['products']['product']
        if not isinstance(xml_products, list):
            xml_products = [xml_products]
        for p in xml_products:
            all_products.append({
                'name': p['name'],
                'price': p['price'],
                'source': 'XML'
            })

    # Extract from JSON
    for p in json_data:
        all_products.append({
            'name': p['name'],
            'price': p['price'],
            'source': 'JSON'
        })

    print("Combined data from XML and JSON:")
    for product in all_products:
        print(f"  {product}")

    # Calculate total
    total = sum(float(p['price']) for p in all_products)
    print(f"\nTotal value: ${total}")


async def main():
    """Run all demos"""
    print("\n" + "="*60)
    print("  CH8 Agent - Data Extraction Skills Demo")
    print("="*60)

    await demo_xml_extraction()
    await demo_json_extraction()
    await demo_csv_extraction()
    await demo_xpath_web()
    await demo_integration()

    print("\n" + "="*60)
    print("  Demo Complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
