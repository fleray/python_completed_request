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

Save result as <YOUR_FILE>.json

Then run:

```
python statement_processor.py <YOUR_FILE>.json
```

The result is stored as Excel sheet in "output_<YOUR_FILE>.xlsx" file containing 5 tabs:

 - TAB 1: Param. Queries - raw queries from completed_request: if "Named" or "Positional" parameters exist, they are left "as is"

 - TAB 2: Param. Queries (Aggregated) - same as previous (TAB 1) but agreggated

 - TAB 3: Normalized Queries (Aggregated) - in this tab <b>all values</b>  get "parametrized": this is to easily group Queries by the "most generic template statement" (i.e. not taking into account any "value"). 

 - TAB 4: Valued Queries - each parameter is replaced by the associated "Named" or "Positional" parameter value

 - TAB 5: Valued Queries (Aggregated) - same as previous (TAB 4) but Aggregated


To conclude:

To my opinion, TAB 3 is the most useful because it gathers all query statements, regardless of their original values.

TAB 4 can be used in case you want to populate a query statement file for [n1qlback](https://docs.couchbase.com/sdk-api/couchbase-c-client-3.3.16/md_doc_2cbc-n1qlback.html) command line tool.