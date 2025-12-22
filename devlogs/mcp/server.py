# MCP server for devlogs

import sys
import json

def search_logs(query=None, area=None, operation_id=None, level=None, since=None, limit=50):
	# TODO: Call shared query logic
	return []

def tail_logs(operation_id=None, area=None, level=None, limit=20):
	# TODO: Call shared tail logic
	return []

def get_operation_summary(operation_id):
	# TODO: Call shared summary logic
	return {}

def main():
	"""Basic stdio MCP server loop."""
	for line in sys.stdin:
		try:
			req = json.loads(line)
			cmd = req.get("command")
			args = req.get("args", {})
			if cmd == "search_logs":
				result = search_logs(**args)
			elif cmd == "tail_logs":
				result = tail_logs(**args)
			elif cmd == "get_operation_summary":
				result = get_operation_summary(**args)
			else:
				result = {"error": "Unknown command"}
			print(json.dumps({"result": result}), flush=True)
		except Exception as e:
			print(json.dumps({"error": str(e)}), flush=True)

if __name__ == "__main__":
	main()
