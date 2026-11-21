# Troubleshooting

| Symptom | Action |
| --- | --- |
| Node works in its install folder but npm is missing | Add the Node install directory to the current PowerShell session PATH, or open a terminal with the installed Node on PATH |
| Spark says Java gateway exited | Check Java 17, JAVA_HOME, an accessible temporary directory and the Python executable. Set PYSPARK_PYTHON to the active Python executable |
| Windows Spark reports permission or native Hadoop errors | Use a permitted loopback session and the intended Windows Hadoop utilities if required. WSL or the Linux container is the alternative to native Spark |
| Dashboard shows API unavailable | Start FastAPI on port 8000, open the configured Vite URL and inspect `/ready` |
| Gold publication blocked | Review the selected run’s quality rules and quarantine. Correct or remove the staged source input and retry |
| Incremental run succeeds with no work | Use a distinct batch number to generate new event IDs. Compare the file manifest and run task messages |
| Lakehouse size falls below raw file size | Parquet uses columnar compression. Inspect the file counts and sizes under the selected snapshot |
| Worker was interrupted | Confirm the previous process exited, inspect the pending run and its log, then run `python -m data_engineering.cli recover` and retry from retained inputs. The prior committed snapshot stays selected |
| Upload returns 422 | Check source filename, file type and flat-data requirements. The selected dataset schema is visible in Data Sources |

Leave failed-run directories available until the incident has been reviewed. The maintenance DAG reports possible cleanup candidates without deleting files.
