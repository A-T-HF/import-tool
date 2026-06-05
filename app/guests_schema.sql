CREATE TABLE IF NOT EXISTS guests (
    custid       INTEGER PRIMARY KEY,
    first_name   TEXT,
    last_name    TEXT,
    email        TEXT,
    salutation   TEXT,
    name_source  TEXT NOT NULL CHECK(name_source IN ('original', 'derived_from_email', 'none')),
    display_name TEXT NOT NULL
);
