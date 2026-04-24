from brin_hotspot.migrations import _strip_psql_meta_commands, list_migration_files


def test_list_migration_files_sorts_sql_files(tmp_path):
    second = tmp_path / "002-second.sql"
    first = tmp_path / "001-first.sql"
    ignored = tmp_path / "notes.txt"
    second.write_text("SELECT 2;", encoding="utf-8")
    first.write_text("SELECT 1;", encoding="utf-8")
    ignored.write_text("ignore", encoding="utf-8")

    assert list_migration_files(tmp_path) == [first, second]


def test_strip_psql_meta_commands():
    sql = "\\connect raster\nSELECT 1;\n  \\echo ignored\nSELECT 2;"

    assert _strip_psql_meta_commands(sql) == "SELECT 1;\nSELECT 2;"
