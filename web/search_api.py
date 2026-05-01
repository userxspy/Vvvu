from aiohttp import web
import time
import re
from utils import temp, get_size
from info import BIN_CHANNEL
from database.ia_filterdb import COLLECTIONS

search_routes = web.RouteTableDef()

def is_admin_logged_in(request):
    session_id = request.cookies.get('admin_session')
    if not hasattr(temp, 'ADMIN_SESSIONS'): return False
    return session_id in temp.ADMIN_SESSIONS and time.time() < temp.ADMIN_SESSIONS[session_id]

@search_routes.get('/api/search')
async def api_search_handler(request):
    if not is_admin_logged_in(request):
        return web.json_response({"error": "Unauthorized Access"}, status=403)

    query = request.query.get('q', '').strip()
    offset = request.query.get('offset', '0')
    target_col = request.query.get('col', 'all').lower() # ✅ नया: कौन सा कलेक्शन खोजना है
    
    try: offset = int(offset)
    except: offset = 0

    if not query:
        return web.json_response({"results": [], "total": 0, "next_offset": ""})

    regex = re.compile(query, re.IGNORECASE)
    filter_query = {"file_name": regex}

    results = []
    total_count = 0
    limit = 20
    needed_docs = offset + limit
    all_matches = []

    # ✅ लॉजिक: अगर 'All' है तो सबमें ढूँढो, वर्ना सिर्फ चुने हुए कलेक्शन में ढूँढो
    cols_to_search = {target_col: COLLECTIONS[target_col]} if target_col in COLLECTIONS else COLLECTIONS

    for col_name, col in cols_to_search.items():
        count = await col.count_documents(filter_query)
        total_count += count
        
        if len(all_matches) < needed_docs:
            cursor = col.find(filter_query).sort('_id', -1).limit(needed_docs)
            async for doc in cursor:
                # यह भी सेव कर लें कि फाइल किस कलेक्शन से आई है (ताकि UI में दिख सके)
                doc['source_col'] = col_name.capitalize() 
                all_matches.append(doc)

    page_docs = all_matches[offset : offset + limit]
    
    for doc in page_docs:
        target_id = doc.get("file_ref", doc.get("file_id"))
        results.append({
            "name": doc.get("file_name", "Unknown File"),
            "size": get_size(doc.get("file_size", 0)),
            "type": doc.get("file_type", "document").upper(),
            "source": doc.get("source_col", "Unknown"), # ✅ नया: कलेक्शन का नाम
            "watch": f"/setup_stream?file_id={target_id}&mode=watch",
            "download": f"/setup_stream?file_id={target_id}&mode=download"
        })
        
    next_offset = (offset + limit) if (offset + limit) < total_count else ""

    return web.json_response({
        "results": results,
        "total": total_count,
        "next_offset": next_offset
    })

@search_routes.get('/setup_stream')
async def setup_stream_handler(request):
    if not is_admin_logged_in(request): return web.Response(text="❌ Unauthorized Access!", status=403)
    file_id = request.query.get('file_id')
    mode = request.query.get('mode', 'watch')
    
    if not file_id: return web.Response(text="Invalid Request", status=400)
    try:
        msg = await temp.BOT.send_cached_media(chat_id=BIN_CHANNEL, file_id=file_id)
        if mode == 'download': raise web.HTTPFound(f"/download/{msg.id}")
        else: raise web.HTTPFound(f"/watch/{msg.id}")
    except web.HTTPFound: raise 
    except Exception as e: return web.Response(text=f"❌ Error: {str(e)}", status=500)
