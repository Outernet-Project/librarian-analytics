import time
import uuid

from dateutil import parser
from psycopg2 import Binary
from bitpack.utils import hex_to_bytes
from bottle_utils.lazy import caching_lazy

from .data import generate_device_id


ANALYTICS_TABLE = 'stats'


# DATABASE OPERATIONS


def prep(data):
    """
    Prepare row data for writing to database. Namely, the 'payload' column is
    marked as binary data.
    """
    data['payload'] = Binary(data['payload'])
    return data


def get_stats(db, limit):
    query = db.Select(sets=ANALYTICS_TABLE, order='time', limit=limit)
    return db.fetchall(query)


def save_stats(db, data):
    prep(data)
    query = db.Insert(ANALYTICS_TABLE, cols=data.keys())
    return db.execute(query, data)


def clear_transmitted(db, ids):
    q = db.Delete(ANALYTICS_TABLE, where='id = %s')
    db.executemany(q, ((i,) for i in ids))


def cleanup_stats(db, max_records):
    query = db.Select('id',
                      sets=ANALYTICS_TABLE,
                      order='-time',
                      offset=max_records,
                      limit=1)
    id_set = db.fetchone(query)
    if not id_set:
        return 0
    delete_query = db.Delete(ANALYTICS_TABLE, where='id <= %s')
    return db.execute(delete_query, id_set)


def merge_streams(stats):
    return b''.join(bytes(s['payload']) for s in stats)


def get_stats_bitstream(db, limit):
    stats = get_stats(db, limit)
    if not stats:
        return [], b''
    bitstream = merge_streams(stats)
    ids = (s['id'] for s in stats)
    return ids, bitstream


# DEVICE ID


@caching_lazy
def prepare_device_id(path):
    try:
        with open(path, 'r') as f:
            current_key = f.read()
    except IOError:
        current_key = ''
    if not current_key:
        # No key has been set yet
        current_key = generate_device_id()
        with open(path, 'w') as f:
            f.write(current_key)
    assert current_key != '', "'My dog ate it' is a poor excuse"
    return current_key


def serialized_device_id(path):
    device_id = prepare_device_id(path)
    return hex_to_bytes(uuid.UUID(str(device_id), version=4).hex)


# PAYLOAD


def get_payload(db, device_id_file, limit):
    ids, bitstream = get_stats_bitstream(db, limit)
    if not ids:
        return ids, bitstream
    device_id = serialized_device_id(device_id_file)
    return ids, device_id + bitstream


# GENERAL HELPERS


def as_time(timestamp):
    """
    Return integer timestamp based on string timestamp.
    """
    dt = parser.parse(timestamp)
    return int(time.mktime(dt.timetuple()))
