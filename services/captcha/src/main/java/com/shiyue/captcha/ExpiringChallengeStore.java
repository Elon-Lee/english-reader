package com.shiyue.captcha;

import cloud.tianai.captcha.cache.CacheStore;
import cloud.tianai.captcha.common.AnyMap;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/** Atomic consume with strict deadlines; bounded memory for this single local service. */
@Component
class ExpiringChallengeStore implements CacheStore {
    private static final int MAX_ENTRIES = 10000;
    private final Map<String, Entry> entries = new LinkedHashMap<>();

    private record Entry(AnyMap value, long deadline) {
        boolean expired() { return System.nanoTime() - deadline >= 0; }
    }

    @Override
    public synchronized AnyMap getCache(String key) {
        Entry entry = entries.get(key);
        if (entry == null) return null;
        if (entry.expired()) {
            entries.remove(key);
            return null;
        }
        return entry.value();
    }

    @Override
    public synchronized AnyMap getAndRemoveCache(String key) {
        Entry entry = entries.remove(key);
        return entry == null || entry.expired() ? null : entry.value();
    }

    @Override
    public synchronized boolean setCache(String key, AnyMap value, Long expire, TimeUnit unit) {
        entries.entrySet().removeIf(item -> item.getValue().expired());
        if (!entries.containsKey(key) && entries.size() >= MAX_ENTRIES) {
            entries.remove(entries.keySet().iterator().next());
        }
        entries.put(key, new Entry(value, System.nanoTime() + unit.toNanos(expire)));
        return true;
    }

    @Override
    public synchronized Long incr(String key, long delta, Long expire, TimeUnit unit) {
        Long existing = getLong(key);
        long value = (existing == null ? 0 : existing) + delta;
        setCache(key, AnyMap.of(Map.of("___incr___", value)), expire, unit);
        return value;
    }

    @Override
    public synchronized Long getLong(String key) {
        AnyMap value = getCache(key);
        return value == null ? null : value.getLong("___incr___");
    }

    @Override
    public synchronized void close() {
        entries.clear();
    }
}
