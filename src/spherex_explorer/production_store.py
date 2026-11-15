"""Durable admission counters and job states for the single-instance demo."""
from pathlib import Path
import sqlite3
import time
from contextlib import contextmanager


class Store:
    def __init__(self, path):
        self.path=Path(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS buckets(name TEXT, window INTEGER, count INTEGER,
                    PRIMARY KEY(name,window));
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, status TEXT,
                    created REAL, finished REAL, message TEXT);
                CREATE TABLE IF NOT EXISTS grants(session TEXT, job TEXT, expires REAL,
                    PRIMARY KEY(session,job));
                CREATE TABLE IF NOT EXISTS owners(job TEXT PRIMARY KEY, session TEXT);
            ''')
            db.execute("UPDATE jobs SET status='error',finished=?,message=? WHERE status='preparing'",
                       (time.time(),'Processing was interrupted by a service restart. Retry explicitly.'))

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=2)
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:yield db
        finally:db.close()

    def admit(self, name, limit, seconds, now=None):
        now=time.time() if now is None else now
        window=int(now//seconds)*seconds
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT count FROM buckets WHERE name=? AND window=?',(name,window)).fetchone()
            if row and row[0]>=limit:return False
            db.execute('INSERT INTO buckets VALUES(?,?,1) ON CONFLICT(name,window) DO UPDATE SET count=count+1',(name,window))
            db.execute('DELETE FROM buckets WHERE window<?',(now-172800,))
            return True

    def job(self, identifier):
        with self.connect() as db:
            row=db.execute('SELECT status,created,finished,message FROM jobs WHERE id=?',(identifier,)).fetchone()
        if not row:return None
        return {'id':identifier,'status':row[0],'created':row[1],'finished':row[2],'message':row[3]}

    def start(self, identifier):
        with self.connect() as db:
            db.execute('DELETE FROM grants WHERE job=?',(identifier,))
            db.execute('DELETE FROM owners WHERE job=?',(identifier,))
            db.execute('INSERT OR REPLACE INTO jobs VALUES(?,?,?,?,?)',
                       (identifier,'preparing',time.time(),None,'Preparing real observations in a bounded worker.'))

    def finish(self, identifier, status, message):
        with self.connect() as db:
            db.execute('UPDATE jobs SET status=?,finished=?,message=? WHERE id=?',
                       (status,time.time(),message,identifier))

    def expired(self, ttl):
        with self.connect() as db:
            return [r[0] for r in db.execute("SELECT id FROM jobs WHERE status!='preparing' AND finished<?",(time.time()-ttl,))]

    def expire(self,identifier):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='expired',message='Assets expired. Request a new preparation explicitly.' WHERE id=?",(identifier,))

    def prune(self):
        with self.connect() as db:
            db.execute("DELETE FROM jobs WHERE status='expired' AND finished<?",(time.time()-172800,))
            db.execute('DELETE FROM grants WHERE expires<?',(time.time(),))
            db.execute('DELETE FROM owners WHERE job NOT IN (SELECT id FROM jobs)')

    def grant(self,session,job,expires,owner=False):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO grants VALUES(?,?,?)',(session,job,expires))
            if owner:db.execute('INSERT OR REPLACE INTO owners VALUES(?,?)',(job,session))

    def permitted(self,session,job,cancel=False):
        with self.connect() as db:
            grant=db.execute('SELECT 1 FROM grants WHERE session=? AND job=? AND expires>?',(session,job,time.time())).fetchone()
            owner=db.execute('SELECT 1 FROM owners WHERE session=? AND job=?',(session,job)).fetchone() if cancel else True
            return bool(grant and owner)


class InstanceLock:
    """OS lock prevents two API processes sharing a quota/workspace."""
    def __init__(self,path):
        self.stream=open(path,'a+b');self.stream.seek(0)
        try:
            if not self.stream.read(1):self.stream.write(b'0');self.stream.flush()
            self.stream.seek(0)
            if __import__('os').name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError('Another backend instance owns this state directory.') from None

    def close(self):
        if not self.stream.closed:self.stream.close()
