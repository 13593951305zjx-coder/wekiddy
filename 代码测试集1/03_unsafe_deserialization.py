import pickle
import yaml


def load_untrusted_data(raw_bytes: bytes, raw_yaml: str):
    # Expected: PY-DESERIALIZE-001 and PY-DESERIALIZE-002
    object_data = pickle.loads(raw_bytes)
    config = yaml.load(raw_yaml)
    return object_data, config

