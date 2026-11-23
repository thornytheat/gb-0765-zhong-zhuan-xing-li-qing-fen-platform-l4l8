from .config import CORE_FILES, FILES, SAMPLES, SAMPLE_NAMES
from .errors import DeskError


def sample(name):
    if name not in SAMPLE_NAMES:
        raise DeskError('NO_SAMPLE', '样例不存在', 404)
    return {file: (SAMPLES / name / file).read_text(encoding='utf-8') if (SAMPLES / name / file).exists() else ''
            for file in FILES}


def submission(body):
    if isinstance(body, dict) and set(body) == {'sample'} and isinstance(body['sample'], str):
        return sample(body['sample'])
    if isinstance(body, dict) and set(body) == {'files'}:
        files = body['files']
        if isinstance(files, dict) and set(files) == set(CORE_FILES) and all(isinstance(text, str) for text in files.values()):
            return {**files, 'retags.csv': ''}
        if isinstance(files, dict) and set(files) == set(FILES) and all(isinstance(text, str) for text in files.values()):
            return files
    raise DeskError('BAD_INPUT', '请选择样例或提交三份 CSV（可附换牌单）')
