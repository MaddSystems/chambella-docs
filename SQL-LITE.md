Install sqlite3 CLI (if not installed):
```
sudo apt-get install sqlite3
```

Open the database:
```
sqlite3 chambella_agent_data.db
```

List tables:
```
.tables
```


Show the schema for sessions:
```
.schema sessions
```

Run your query to see the values:
```
SELECT s.user_id, s.state, MAX(s.update_time) as last_access
FROM sessions s WHERE s.app_name = 'Jobs Support' GROUP BY s.user_id;
```

(Optional) See all rows:

SELECT * FROM sessions;