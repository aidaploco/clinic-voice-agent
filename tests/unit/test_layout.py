from collections import Counter
from pathlib import Path


def test_no_two_test_files_share_a_name():
    # The test folders have no package files, so pytest imports each file by its bare name and
    # refuses a second one with the same name. That showed up only in CI, which collects every
    # folder, while a run of one folder passed.
    names = Counter(path.name for path in Path("tests").rglob("test_*.py"))
    assert [name for name, count in names.items() if count > 1] == []
