from aiohttp import web
import time
from database.ia_filterdb import get_search_results # ✅ नया: जो पेजिंग (Next) को सपोर्ट करता है
from utils import temp, get_size
from info import BIN_CHANNEL

search_routes = web.RouteTableDef()

# ─────────────────────────────────────────────
# 🔒 SECURITY CHECK
# ─────────────────────────────────────────────
def is_admin_logged_in(request):
    session_id = request.cookies.get('admin_session')
    if not hasattr(temp, 'ADMIN_SESSIONS'):
        return False
    if not session_id or session_id not in temp.ADMIN_SESSIONS:
        return False
    if time.time() > temp.ADMIN_SESSIONS[session_id]:
        del temp.ADMIN_SESSIONS[session_id]
        return False
    return True

# ─────────────────────────────────────────────
# 📡 BACKEND API (WITH PAGINATION & TOTAL COUNT)
# ─────────────────────────────────────────────
@search_routes.get('/api/search')
async def api_search_handler(request):
    if not is_admin_logged_in(request):
        return web.json_response({"error": "Unauthorized Access"}, status=403)

    query = request.query.get('q', '').strip()
    offset = request.query.get('offset', '0')
    
    try: offset = int(offset)
    except: offset = 0

    if not query:
        return web.json_response({"results": [], "total": 0, "next_offset": ""})

    # डेटाबेस से सर्च रिज़ल्ट्स, अगला पेज नंबर और टोटल फाइल्स लाएं (Max 20 per page)
    docs, next_offset, total, _ = await get_search_results(query, max_results=20, offset=offset, collection_type="all")
    
    results = []
    for doc in docs:
        target_id = doc.get("file_ref", doc.get("file_id"))
        results.append({
            "name": doc.get("file_name", "Unknown File"),
            "size": get_size(doc.get("file_size", 0)),
            "type": doc.get("file_type", "document").upper(),
            "watch": f"/setup_stream?file_id={target_id}&mode=watch",
            "download": f"/setup_stream?file_id={target_id}&mode=download"
        })
        
    return web.json_response({
        "results": results,
        "total": total,
        "next_offset": next_offset
    })

# ─────────────────────────────────────────────
# 🌉 STREAM BRIDGE
# ─────────────────────────────────────────────
@search_routes.get('/setup_stream')
async def setup_stream_handler(request):
    if not is_admin_logged_in(request):
        return web.Response(text="❌ Unauthorized Access!", status=403)
        
    file_id = request.query.get('file_id')
    mode = request.query.get('mode', 'watch')
    
    if not file_id: return web.Response(text="Invalid Request", status=400)
        
    try:
        msg = await temp.BOT.send_cached_media(chat_id=BIN_CHANNEL, file_id=file_id)
        if mode == 'download': raise web.HTTPFound(f"/download/{msg.id}")
        else: raise web.HTTPFound(f"/watch/{msg.id}")
            
    except web.HTTPFound: raise 
    except Exception as e: return web.Response(text=f"❌ Error: {str(e)}", status=500)
