import os
import sys
from app.services.text_to_sql_service import TextToSQLService

try:
    service = TextToSQLService()
    template = service._load_prompt_template()
    prompt = template.format(question="test", schema_context="schema", metric_context="metrics")
    print("Format successful!")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
