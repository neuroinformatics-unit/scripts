from pathlib import Path
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors
import pooch

INPUT_FILE = "./download_by_country.csv"
OUTPUT_DIR = "./figures"
CMAP = 'viridis'
TIMEPERIOD = 'year'
BG_ONLY = True
NORMALISE_POPULATION = False
POPULATION_DATA = './WPP2022_Demographic_Indicators_Medium.csv' # Source: https://population.un.org/wpp/Download/Files/1_Indicators%20(Standard)/CSV_FILES/WPP2022_Demographic_Indicators_Medium.zip
BG_PACKAGES = [
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
    'brainreg-segment',
    'bgheatmap',
    'morphapi',
    'cellfinder-visualize',
    'bg-space',
]


def fetch_shapefile():
    url = "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/world-administrative-boundaries/exports/shp?lang=en&timezone=Europe%2FLondon"
    fname = pooch.retrieve(
        url,
        known_hash=None,
        processor=pooch.Unzip()
    )

    shapefile = [f for f in fname if f.endswith('.shp')][0]

    return shapefile


def fetch_population(file_name: str, year: int = 2024):
    population_df = pd.read_csv(file_name, low_memory=False)
    population_df = population_df[population_df['Time'] == year]
    population_df = population_df[['ISO3_code', 'ISO2_code', 'Location', 'TPopulation1Jan']]

    return population_df


def create_plot(merged_df: gpd.GeoDataFrame, col: str, file_name: str, title: str, cmap: str, log_scale: bool, annotation: str = ""):
    vmin = 0.0001
    vmax = merged_df[col].max()
    norm = matplotlib.colors.LogNorm(vmin=vmin, vmax=vmax)

    if not log_scale:
        norm = plt.Normalize(vmin, vmax)

    # Create figure and axes for Matplotlib
    fig, ax = plt.subplots(1, figsize=(20, 8))
    # Remove the axis
    ax.axis('off')
    merged_df.plot(column=col, ax=ax, edgecolor='0.8', linewidth=0.25,
                   norm=norm, cmap=cmap, missing_kwds={'color': 'white'})
    # Add a title
    ax.set_title(title, fontdict={'fontsize': '25', 'fontweight': '3'})
    if len(annotation) > 0:
        ax.annotate(annotation, xy=(0.1, .08), xycoords='figure fraction', horizontalalignment='left',
                    verticalalignment='bottom', fontsize=10)

    # Create colorbar as a legend
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    # Empty array for the data range
    sm._A = []
    # Add the colorbar to the figure
    cbaxes = fig.add_axes([0.15, 0.25, 0.01, 0.4])
    cbar = fig.colorbar(sm, cax=cbaxes)
    plt.savefig(file_name, dpi=300, bbox_inches='tight')
    plt.close(fig)


master_df = pd.read_csv(INPUT_FILE)
geo_df = gpd.read_file(fetch_shapefile())
col = 'num_downloads'
log_scale = False
annotation = ""

if BG_ONLY:
    master_df = master_df[master_df['project'].isin(BG_PACKAGES)]

if NORMALISE_POPULATION:
    pop_df = fetch_population(POPULATION_DATA)
    master_df = pd.merge(master_df, pop_df, how='left', left_on='country_code', right_on='ISO2_code')
    col = 'normalised_downloads'
    master_df[col] = master_df['num_downloads'] / (master_df['TPopulation1Jan'] / 100)
    log_scale = False
    annotation = "Downloads per 100,000 residents"

Path(OUTPUT_DIR).mkdir(exist_ok=True)

# Create an overall figure for all repositories
merged_df = pd.merge(left=geo_df, right=master_df.groupby('country_code').sum(col), how='left', left_on='iso_3166_1_', right_on='country_code')
# merged_df[col].fillna(0, inplace=True)

title = f"Total downloads for all packages in the last {TIMEPERIOD}"
output_file = f'{OUTPUT_DIR}/all_by_country.png'
create_plot(merged_df, col, output_file, title, CMAP, log_scale, annotation)

# Create a figure for each package
# List of package names to query
package_names = master_df['project'].unique()

for name in package_names:
    merged_df = pd.merge(left=geo_df, right=master_df[master_df['project'] == name], how='left',
                         left_on='iso_3166_1_', right_on='country_code')
    # merged_df[col].fillna(0, inplace=True)
    title = f"{name} downloads in the last {TIMEPERIOD}"
    output_file = f'{OUTPUT_DIR}/{name}_by_country.png'

    create_plot(merged_df, col, output_file, title, CMAP, log_scale, annotation)
