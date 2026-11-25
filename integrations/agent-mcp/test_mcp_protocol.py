"""Real stdio MCP discovery and tool call against an isolated fake Desk-Pal."""
import asyncio
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            received.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'status':'received' if self.path.endswith('event') else 'ok'}).encode())
        def do_GET(self):
            self.send_response(200);self.end_headers();self.wfile.write(b'{"state":"idle","pending":[]}')
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try:
        with tempfile.TemporaryDirectory() as directory:
            parameters=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).with_name('server.py').resolve()),'--deskpal','http://127.0.0.1:'+str(http.server_port),'--state-dir',directory])
            async with stdio_client(parameters) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    tools=await session.list_tools()
                    assert {t.name for t in tools.tools}=={'deskpal_report_activity','deskpal_get_status'}
                    result=await session.call_tool('deskpal_report_activity',{'activity':'completed','task_id':'protocol-test','message':'Test task completed','occurrence_id':'protocol-test-done'})
                    assert not result.isError, result
                    data=json.loads(result.content[0].text)
                    assert data['delivery']=='received',data
                    assert received[0][1]['event']=='task_completed'
                    result=await session.call_tool('deskpal_get_status',{})
                    assert not result.isError,result
                    assert json.loads(result.content[0].text)['reachable'] is True
                    bad=await session.call_tool('deskpal_report_activity',{'activity':'invented','task_id':'x','message':'x','occurrence_id':'x'})
                    assert bad.isError
                    assert len(received)==2
            assert len(list(Path(directory).glob('*.json')))==1
    finally:
        http.shutdown();http.server_close();thread.join()
    print('Real MCP initialize, tool discovery, report, status and invalid-input checks passed.')


if __name__=='__main__':
    asyncio.run(main())
