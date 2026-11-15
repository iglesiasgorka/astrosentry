"""Server-issued anonymous capabilities; no public credential or unbounded acquisition."""
import hashlib
import hmac
import re
import secrets
import time


class DemoSessions:
    def __init__(self,key,until):self.key=key.encode();self.until=until

    def issue(self):
        payload=f'{secrets.token_urlsafe(18)}.{int(min(time.time()+21600,self.until))}'
        signature=hmac.new(self.key,('session:'+payload).encode(),hashlib.sha256).hexdigest()
        return payload+'.'+signature

    def read(self,token):
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{24}\.\d{10}\.[a-f0-9]{64}',token):return None
        payload,signature=token.rsplit('.',1);expires=int(payload.rsplit('.',1)[1])
        expected=hmac.new(self.key,('session:'+payload).encode(),hashlib.sha256).hexdigest()
        if not time.time()<expires<=self.until or not hmac.compare_digest(signature,expected):return None
        return hashlib.sha256(token.encode()).hexdigest(),expires
