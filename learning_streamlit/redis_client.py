import redis
import pickle
import time


class RedisSaver:
    def __init__(self, redis_url="redis://localhost:6379"):
        self.r = redis.from_url(redis_url)

    def save(self, key, state):
        self.r.set(key, pickle.dumps(state))

    def load(self, key):
        data = self.r.get(key)
        if data:
            return pickle.loads(data)
        return None

    def get_next_version(self, key):
        # Pregel needs this; just a timestamp is fine
        return int(time.time() * 1000)

    def put_writes(self, writes):
        for key, state in writes.items():
            self.save(key, state)
