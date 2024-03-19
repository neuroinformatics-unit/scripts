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


def fetch_shapefile():
    url = "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/world-administrative-boundaries/exports/shp?lang=en&timezone=Europe%2FLondon"
    fname = pooch.retrieve(
        url,
        known_hash=None,
        processor=pooch.Unzip()
    )

    shapefile = [f for f in fname if f.endswith('.shp')][0]

    return shapefile


def create_plot(merged_df: gpd.GeoDataFrame, col: str, file_name: str, title: str, cmap: str):
    vmin = 1
    vmax = merged_df[col].max()

    # Create figure and axes for Matplotlib
    fig, ax = plt.subplots(1, figsize=(20, 8))
    # Remove the axis
    ax.axis('off')
    merged_df.plot(column=col, ax=ax, edgecolor='0.8', linewidth=0.25,
                   norm=matplotlib.colors.LogNorm(vmin=vmin, vmax=vmax), cmap=cmap)
    # Add a title
    ax.set_title(title, fontdict={'fontsize': '25', 'fontweight': '3'})
    # Create colorbar as a legend
    sm = plt.cm.ScalarMappable(norm=matplotlib.colors.LogNorm(vmin=vmin, vmax=vmax), cmap=cmap)
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

Path(OUTPUT_DIR).mkdir(exist_ok=True)

# Create an overall figure for all repositories
merged_df = pd.merge(left=geo_df, right=master_df.groupby('country_code').sum('num_downloads'), how='left', left_on='iso_3166_1_', right_on='country_code')
merged_df.fillna(0, inplace=True)

title = f"Total downloads for all packages in the last {TIMEPERIOD}"
output_file = f'{OUTPUT_DIR}/all_by_country.png'
create_plot(merged_df, col, output_file, title, CMAP)


# Create a figure for each package
package_names = master_df['project'].unique()

for name in package_names:
    merged_df = pd.merge(left=geo_df, right=master_df[master_df['project'] == name], how='left',
                         left_on='iso_3166_1_', right_on='country_code')
    merged_df.fillna(0, inplace=True)
    title = f"{name} downloads in the last {TIMEPERIOD}"
    output_file = f'{OUTPUT_DIR}/{name}_by_country.png'

    create_plot(merged_df, col, output_file, title, CMAP)
