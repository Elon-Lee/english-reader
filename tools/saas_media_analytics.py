"""Read-only inventory totals and bounded registration history for administrators."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from saas_auth import SaaSError

TIMEZONE = 'Asia/Shanghai'


def period_range(period, start='', end='', today=None):
    if period not in {'day', 'month', 'year'}:
        raise SaaSError('invalid_media_period', '请选择按天、按月或按年统计。', 400)
    today = today or datetime.now(ZoneInfo(TIMEZONE)).date()
    finish = today
    begin = today - timedelta(days=29) if period == 'day' else (
        date(today.year - 1, today.month, 1) + timedelta(days=32) if period == 'month' else date(today.year - 4, 1, 1))
    if period == 'month':
        begin = begin.replace(day=1)
    try:
        if start: begin = date.fromisoformat(start)
        if end: finish = date.fromisoformat(end)
    except (ValueError, TypeError):
        raise SaaSError('invalid_media_range', '统计日期格式应为 YYYY-MM-DD。', 400)
    if begin > finish or begin.year < 1970 or finish > today:
        raise SaaSError('invalid_media_range', '请选择有效的统计日期范围，结束日期不能晚于今天。', 400)
    bucket = lambda value: value if period == 'day' else value.replace(day=1) if period == 'month' else value.replace(month=1, day=1)
    current, last, buckets = bucket(begin), bucket(finish), []
    while current <= last:
        buckets.append(current.isoformat())
        if len(buckets) > {'day': 366, 'month': 120, 'year': 20}[period]:
            raise SaaSError('media_range_too_large', '最多查看 366 天、120 个月或 20 年，请缩小范围。', 400)
        current = (current + timedelta(days=1) if period == 'day' else
                   date(current.year + (current.month == 12), current.month % 12 + 1, 1) if period == 'month' else
                   date(current.year + 1, 1, 1))
    return begin, finish, buckets


def media_statistics(accounts, period='day', start='', end=''):
    begin, finish, buckets = period_range(period, start, end)
    with accounts.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT COUNT(*) AS assets,COUNT(DISTINCT owner_id) AS owners,
                COALESCE(SUM(original_bytes),0) AS original,
                COALESCE(SUM(generated_bytes),0) AS generated,
                COALESCE(SUM(original_bytes+generated_bytes) FILTER (WHERE scope='private'),0) AS private,
                COALESCE(SUM(original_bytes+generated_bytes) FILTER (WHERE scope='official'),0) AS official
                FROM media_assets WHERE status='active'""")
            totals = accounts._one(cursor)
            cursor.execute("SELECT COUNT(*) AS variants FROM asset_variants v JOIN media_assets a ON a.id=v.asset_id WHERE a.status='active' AND v.deleted_at IS NULL")
            variants = int(accounts._one(cursor)['variants'])
            # Originals and variants are separate events: never double count generated_bytes.
            # Retain deleted registrations in history; totals above are only current active assets.
            cursor.execute("""WITH events AS (
                SELECT created_at,original_bytes AS bytes,1 AS assets,0 AS variants FROM media_assets
                UNION ALL SELECT created_at,byte_size,0,1 FROM asset_variants
            ) SELECT date_trunc(%s,created_at AT TIME ZONE %s)::date AS bucket,
                SUM(bytes) AS bytes,SUM(assets) AS assets,SUM(variants) AS variants FROM events
                WHERE created_at >= (%s::date::timestamp AT TIME ZONE %s)
                AND created_at < ((%s::date+1)::timestamp AT TIME ZONE %s)
                GROUP BY bucket ORDER BY bucket""", (period, TIMEZONE, begin, TIMEZONE, finish, TIMEZONE))
            rows = {row['bucket'].isoformat(): row for row in accounts._many(cursor)}
    history = [{'date': key, **{field: int(rows.get(key, {}).get(field, 0)) for field in ('bytes', 'assets', 'variants')}} for key in buckets]
    return {'timezone': TIMEZONE, 'period': period, 'start': begin.isoformat(), 'end': finish.isoformat(),
            'summary': {'assetCount': int(totals['assets']), 'ownerCount': int(totals['owners']), 'variantCount': variants,
                        'originalBytes': int(totals['original']), 'generatedBytes': int(totals['generated']),
                        'totalBytes': int(totals['original']) + int(totals['generated']),
                        'privateBytes': int(totals['private']), 'officialBytes': int(totals['official'])},
            'history': history}
