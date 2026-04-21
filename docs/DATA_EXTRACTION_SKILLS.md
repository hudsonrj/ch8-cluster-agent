# Data Extraction Skills - Pre-built Agents

**Data:** 2026-04-21
**Status:** Ready to Use

---

## 📚 Overview

CH8 Agent inclui agentes pré-fabricados especializados em extração de dados de diversos formatos. Eles são **skills prontos** que podem ser usados imediatamente pelos nós.

### Agentes Disponíveis:

1. **XMLExtractorAgent** - XML parsing e XPath
2. **JSONExtractorAgent** - JSON parsing e JSONPath
3. **CSVExtractorAgent** - CSV parsing e análise
4. **ParquetExtractorAgent** - Parquet reading otimizado
5. **XPathExtractorAgent** - XPath queries em XML/HTML

---

## 🔧 Installation

```bash
# Instalar dependências
pip install lxml jsonpath-ng pandas pyarrow chardet
```

---

## 📖 Quick Start

### Example 1: Extract from XML

```python
from cluster.skills.data_extraction import XMLExtractorAgent

# Create extractor
xml_agent = XMLExtractorAgent()

# Extract using XPath
data = await xml_agent.extract('data.xml', {
    'xpath': '//product[@category="electronics"]',
    'output_format': 'dict'
})

# Extract all elements with specific tag
products = await xml_agent.extract_all_elements('data.xml', 'product')

# Extract by attribute
active_users = await xml_agent.extract_by_attribute(
    'users.xml',
    tag_name='user',
    attr_name='status',
    attr_value='active'
)
```

### Example 2: Extract from JSON

```python
from cluster.skills.data_extraction import JSONExtractorAgent

json_agent = JSONExtractorAgent()

# Extract using JSONPath
items = await json_agent.extract('data.json', {
    'jsonpath': '$.store.books[*].title'
})

# Extract with filter
active_users = await json_agent.extract('users.json', {
    'jsonpath': '$.users[*]',
    'filter': lambda x: x['active'] == True
})

# Flatten nested JSON
flat_data = await json_agent.extract('nested.json', {
    'flatten': True
})

# Convert to CSV
csv_output = await json_agent.extract('data.json', {
    'output_format': 'csv'
})
```

### Example 3: Extract from CSV

```python
from cluster.skills.data_extraction import CSVExtractorAgent

csv_agent = CSVExtractorAgent()

# Extract specific columns
data = await csv_agent.extract_columns('sales.csv', ['date', 'amount', 'region'])

# Filter rows
high_value = await csv_agent.filter_rows(
    'sales.csv',
    lambda row: row['amount'] > 1000
)

# Aggregate data
summary = await csv_agent.aggregate(
    'sales.csv',
    groupby='region',
    aggregations={'amount': 'sum', 'orders': 'count'}
)

# Get column statistics
stats = await csv_agent.get_column_stats('sales.csv', 'amount')

# Convert to JSON
await csv_agent.csv_to_json('data.csv', 'output.json')
```

### Example 4: Extract from Parquet

```python
from cluster.skills.data_extraction import ParquetExtractorAgent

parquet_agent = ParquetExtractorAgent()

# Column projection (efficient!)
data = await parquet_agent.extract_columns('data.parquet', ['col1', 'col2'])

# Predicate pushdown (very efficient!)
filtered = await parquet_agent.filter_rows(
    'data.parquet',
    filters=[
        ('age', '>', 18),
        ('status', '==', 'active')
    ]
)

# Get schema
schema = await parquet_agent.get_schema('data.parquet')

# Get statistics without reading full file
stats = await parquet_agent.extract_statistics('data.parquet', 'amount')

# Convert to CSV
await parquet_agent.convert_to_csv('data.parquet', 'output.csv')
```

### Example 5: XPath Extraction

```python
from cluster.skills.data_extraction import XPathExtractorAgent

xpath_agent = XPathExtractorAgent()

# Extract from XML
titles = await xpath_agent.extract('books.xml', {
    'xpath': '//book/title/text()'
})

# Extract from HTML
prices = await xpath_agent.extract('product.html', {
    'xpath': '//span[@class="price"]/text()',
    'content_type': 'html'
})

# Web scraping
product_data = await xpath_agent.scrape_website(
    'https://example.com/product',
    patterns={
        'title': '//h1/text()',
        'price': '//span[@class="price"]/text()',
        'description': '//div[@class="desc"]/text()',
        'images': '//img/@src'
    }
)

# Extract all links
links = await xpath_agent.extract_links('page.html', base_url='https://example.com')

# Extract tables
tables = await xpath_agent.extract_tables('data.html')
```

---

## 🔌 Using in Agent Nodes

### Integration with AgentNode

```python
# cluster/agent_node.py

class AgentNode:

    async def start(self):
        # Load data extraction skills
        self.data_extractors = {
            'xml': XMLExtractorAgent(),
            'json': JSONExtractorAgent(),
            'csv': CSVExtractorAgent(),
            'parquet': ParquetExtractorAgent(),
            'xpath': XPathExtractorAgent()
        }

    async def process_data_extraction_task(self, task):
        """Process data extraction task"""

        file_path = task.params['file_path']
        file_type = task.params['file_type']
        query = task.params.get('query', {})

        # Select appropriate extractor
        extractor = self.data_extractors[file_type]

        # Extract data
        result = await extractor.extract(file_path, query)

        return result
```

### Configuration

```yaml
# config/node.yaml

skills:
  data_extraction:
    enabled: true
    agents:
      - xml
      - json
      - csv
      - parquet
      - xpath

    settings:
      max_file_size: "100MB"
      chunk_size: 1000
      timeout: 300
```

---

## 🎯 Use Cases

### Use Case 1: ETL Pipeline

```python
async def etl_pipeline(input_file: str, output_format: str):
    """Extract, Transform, Load pipeline"""

    # 1. Extract from source
    if input_file.endswith('.xml'):
        data = await xml_agent.extract(input_file)
    elif input_file.endswith('.json'):
        data = await json_agent.extract(input_file)
    elif input_file.endswith('.csv'):
        data = await csv_agent.extract(input_file)
    elif input_file.endswith('.parquet'):
        data = await parquet_agent.extract(input_file)

    # 2. Transform (using LLM)
    transformed = await llm.transform(data, instructions="Clean and normalize")

    # 3. Load to target format
    if output_format == 'json':
        with open('output.json', 'w') as f:
            json.dump(transformed, f)
    elif output_format == 'csv':
        pd.DataFrame(transformed).to_csv('output.csv')
```

### Use Case 2: Web Scraping + Data Analysis

```python
async def scrape_and_analyze(url: str):
    """Scrape website and analyze data"""

    # 1. Scrape data
    products = await xpath_agent.scrape_website(url, {
        'name': '//h2[@class="product-name"]/text()',
        'price': '//span[@class="price"]/text()',
        'rating': '//div[@class="rating"]/@data-rating'
    })

    # 2. Convert to DataFrame for analysis
    df = pd.DataFrame(products)

    # 3. Analyze with LLM
    analysis = await llm.analyze(
        df.to_dict(),
        question="What are the pricing trends?"
    )

    return analysis
```

### Use Case 3: Multi-Format Data Aggregation

```python
async def aggregate_multi_format(sources: List[Dict]):
    """Aggregate data from multiple formats"""

    all_data = []

    for source in sources:
        file_path = source['path']
        file_type = source['type']

        # Extract based on type
        if file_type == 'xml':
            data = await xml_agent.extract(file_path)
        elif file_type == 'json':
            data = await json_agent.extract(file_path)
        elif file_type == 'csv':
            data = await csv_agent.extract(file_path)
        elif file_type == 'parquet':
            data = await parquet_agent.extract(file_path)

        all_data.extend(data)

    # Aggregate
    df = pd.DataFrame(all_data)
    summary = df.groupby('category').agg({'amount': 'sum'})

    return summary
```

### Use Case 4: Real-time Data Processing

```python
async def process_streaming_data(file_path: str):
    """Process large file in chunks"""

    # Process CSV in chunks
    async for chunk in csv_agent.extract(file_path, {
        'chunksize': 1000,
        'output_format': 'dataframe'
    }):
        # Process each chunk
        processed = await llm.process(chunk.to_dict())

        # Save results incrementally
        await save_to_db(processed)
```

---

## 🚀 Advanced Features

### Custom Extractors

```python
from cluster.skills.data_extraction import BaseExtractorAgent

class CustomFormatAgent(BaseExtractorAgent):
    """Custom extractor for proprietary format"""

    def _define_capabilities(self):
        return ["parse_custom", "extract_fields"]

    def _get_supported_formats(self):
        return [".custom", ".prop"]

    async def extract(self, source, query=None):
        # Custom extraction logic
        pass
```

### Chaining Extractors

```python
async def chain_extraction(file_path: str):
    """Chain multiple extractors"""

    # 1. Extract XML
    xml_data = await xml_agent.extract(file_path)

    # 2. Convert to JSON
    json_data = json.dumps(xml_data)

    # 3. Extract with JSONPath
    result = await json_agent.extract(json_data, {
        'jsonpath': '$.data[*].items'
    })

    return result
```

### Parallel Extraction

```python
async def parallel_extraction(files: List[str]):
    """Extract from multiple files in parallel"""

    tasks = []
    for file in files:
        if file.endswith('.xml'):
            tasks.append(xml_agent.extract(file))
        elif file.endswith('.json'):
            tasks.append(json_agent.extract(file))
        elif file.endswith('.csv'):
            tasks.append(csv_agent.extract(file))

    results = await asyncio.gather(*tasks)
    return results
```

---

## 📊 Performance Tips

### XML/XPath
- ✅ Use specific XPath instead of `//` when possible
- ✅ Extract attributes with `/@attr` (faster than full element)
- ✅ For HTML, use `lxml.html` (faster than XML parser)

### JSON
- ✅ Use JSONPath for nested extraction (faster than manual navigation)
- ✅ Stream large files with JSON Lines format
- ✅ Flatten only when necessary (can be expensive)

### CSV
- ✅ Use column projection (read only needed columns)
- ✅ Use chunked reading for files > 100MB
- ✅ Detect delimiter/encoding once and reuse
- ✅ Use pandas for aggregations (C-optimized)

### Parquet
- ✅ Always use column projection (major performance boost)
- ✅ Use predicate pushdown for filtering (reads less data)
- ✅ Read statistics from metadata (no file read needed)
- ✅ For large files, read only needed row groups

---

## 🔗 MCP Integration

These extractors can be exposed as MCP Integration Agents:

```python
# cluster/integration/data_extraction_mcp.py

class DataExtractionMCPAgent(MCPIntegrationAgent):
    """MCP wrapper for data extraction agents"""

    def __init__(self, config):
        super().__init__(config)
        self.extractors = {
            'xml': XMLExtractorAgent(),
            'json': JSONExtractorAgent(),
            'csv': CSVExtractorAgent(),
            'parquet': ParquetExtractorAgent(),
            'xpath': XPathExtractorAgent()
        }

    async def execute_action(self, action, params):
        """Execute extraction action"""

        file_type = params['file_type']
        file_path = params['file_path']
        query = params.get('query', {})

        extractor = self.extractors[file_type]
        return await extractor.extract(file_path, query)
```

Now nodes can share extraction capabilities via P2P!

---

## 📚 API Reference

See individual agent files for complete API:

- `xml_extractor.py` - XMLExtractorAgent
- `json_extractor.py` - JSONExtractorAgent
- `csv_extractor.py` - CSVExtractorAgent
- `parquet_extractor.py` - ParquetExtractorAgent
- `xpath_extractor.py` - XPathExtractorAgent

---

**Status:** Production Ready
**Author:** Hudson RJ + Claude
**Date:** 2026-04-21
