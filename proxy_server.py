#!/usr/bin/env python3
"""
Simple OpenAI Authentication Proxy Server using Sanic
Passes through all requests to destination with Azure AD token
"""

import os
import asyncio
import threading
from datetime import datetime, timedelta
import aiohttp
from sanic import Sanic, Request, response
from azure.identity import CertificateCredential

class TokenManager:
    def __init__(self):
        self.token = None
        self.expires_at = None
        self.lock = threading.Lock()
        
        # Azure AD config from env
        self.client_id = os.getenv('AZURE_CLIENT_ID')
        self.cert_path = os.getenv('AZURE_CERTIFICATE_PATH')
        self.tenant_id = os.getenv('AZURE_TENANT_ID')
        self.scope = os.getenv('AZURE_SCOPE', 'https://cognitiveservices.azure.com/.default')
        
        # Get initial token
        self._refresh_token()
        
        # Start background refresh
        self._start_refresh_timer()
    
    def get_token(self):
        with self.lock:
            if self._needs_refresh():
                self._refresh_token()
            return self.token
    
    def _needs_refresh(self):
        if not self.token or not self.expires_at:
            return True
        # Refresh 5 minutes before expiry
        return datetime.utcnow() >= (self.expires_at - timedelta(minutes=5))
    
    def _refresh_token(self):
        credential = CertificateCredential(
            client_id=self.client_id,
            certificate_path=self.cert_path,
            tenant_id=self.tenant_id
        )
        token_response = credential.get_token(self.scope)
        self.token = token_response.token
        # Azure tokens typically last 1 hour
        self.expires_at = datetime.utcnow() + timedelta(seconds=3600)
        print(f"Token refreshed, expires at: {self.expires_at}")
    
    def _start_refresh_timer(self):
        def refresh_loop():
            while True:
                asyncio.sleep(30 * 60)  # Check every 30 minutes
                with self.lock:
                    if self._needs_refresh():
                        try:
                            self._refresh_token()
                        except Exception as e:
                            print(f"Token refresh failed: {e}")
        
        thread = threading.Thread(target=refresh_loop, daemon=True)
        thread.start()

# Initialize
app = Sanic("auth-proxy")
token_manager = TokenManager()
destination_url = os.getenv('API_BASE_URL').rstrip('/')
timeout = aiohttp.ClientTimeout(total=120)

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
async def proxy_all(request: Request, path: str):
    """Proxy all requests to destination with auth token"""
    
    # Get fresh token
    access_token = token_manager.get_token()
    
    # Build target URL
    target_url = f"{destination_url}/{path}"
    # Copy headers and add auth
    headers = dict(request.headers)
    
    headers['Authorization'] = f'Bearer {access_token}'
    
    # Remove hop-by-hop headers
    for h in ['host', 'content-length', 'connection']:
        headers.pop(h, None)
    
    # Get request data
    data = None
    if request.method in ['POST', 'PUT', 'PATCH'] and request.body:
        data = request.body
        if request.content_type and 'json' in request.content_type:
            headers['Content-Type'] = 'application/json'
    # Make proxied request
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=data,
            params=dict(request.args)
        ) as resp:
            body = await resp.read()
            return response.raw(body, status=resp.status, headers=dict(resp.headers))

# Health check
@app.get('/health')
async def health(request):
    return response.json({'status': 'ok'})

if __name__ == '__main__':
    app.run(
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', '8080')),
        workers=1
    )