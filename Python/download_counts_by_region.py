"""
Command-line script for querying the public pypi dataset for regional download stats.

Prerequisites:
1. Make sure that BigQuery is enabled for your project: https://cloud.google.com/bigquery/docs/quickstarts/quickstart-client-libraries
2. Install google cloud bigquery: https://cloud.google.com/bigquery/docs/reference/libraries
    This can be done with `pip install google-cloud-bigquery`.
3. Install and initialize the gcloud CLI: https://cloud.google.com/sdk/docs/install
4. Set up application default credentials.
    This can be done with `gcloud auth application-default login`.
5. Install the Python dependencies: `pip install pandas db-dtypes`
"""

from google.cloud import bigquery
import pandas as pd

# Set the output directory
OUTPUT_FILE = "./download_by_country.csv"

# List of package names to query
PACKAGE_NAMES = [
    'movement',
    'brainglobe-atlasapi',
    'brainglobe',
    'brainrender-napari',
    'brainrender',
    'brainglobe-napari-io',
    'brainreg',
    'brainglobe-segmentation',
    'brainglobe-utils',
    'cellfinder',
    'brainglobe-workflows',
    'imio',
    'brainglobe-template-builder',
    'bg-atlasapi',
    'brainglobe-space',
    'brainreg-napari',
    'cellfinder-napari',
    'cellfinder-core',
    'brainmapper',
    'slurmio',
    'brainreg-segment',
    'bgheatmap',
    'morphapi',
    'datashuttle',
    'cellfinder-visualize',
    'fancylog',
    'bg-space',
]

# Set the time period to query in days
query_timeperiod_start = 0
query_timeperiod_end = 1

client = bigquery.Client()
query_job = client.query(
    f"""
        SELECT file.project, country_code, COUNT(*) AS num_downloads, 
        FROM `bigquery-public-data.pypi.file_downloads`
        WHERE file.project IN {tuple(PACKAGE_NAMES)}
          AND DATE(timestamp)
            BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL {query_timeperiod_end} DAY)
            AND DATE_SUB(CURRENT_DATE(), INTERVAL {query_timeperiod_start} DAY)
        GROUP BY country_code, file.project
    """
)

results = query_job.result()  # Waits for job to complete.
df = results.to_dataframe()
df.to_csv(OUTPUT_FILE, index=False)
