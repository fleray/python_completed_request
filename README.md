# python_completed_request
Extract and sort queries from completed_request in an XLS file

```
pip install -r requirements.txt
```

Input file is the JSON result from :

```
SELECT completed_requests.*
FROM system:completed_requests
WHERE UPPER(statement)NOT LIKE 'ADVISE %'
  AND UPPER(statement) NOT LIKE 'INFER %'
  AND UPPER(statement) NOT LIKE 'CREATE INDEX%'
  AND UPPER(statement) NOT LIKE '% SYSTEM:%'
  AND UPPER(statement) NOT LIKE 'EXPLAIN %'
--  AND requestTime > "2025-05-13T17:21:00.000Z" AND requestTime < "2025-05-17T37:00:00.000Z" -- eventually filtered on a given data range interval
ORDER BY requestTime DESC
```

Save result as foo.json

Then run:

```
python statement_processor.py foo.json
```
