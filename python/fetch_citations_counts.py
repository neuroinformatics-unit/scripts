"""Fetch citation counts for a list of tools from OpenAlex and save to CSV.

The input is a dictionary mapping each tool to a a list of DOIs
(some tools have >1 citable objects, e.g. preprint + peer-reviewed paper).
The script uses the OpenAlex API to fetch citation counts for each DOI and
sums them up for each tool. The output is a CSV file containing the total
number of citations for each tool.

Please edit the EMAIL and the TOOLS_TO_PUBS variables below
before running the script.

Dependencies:
- pyalex (a Python API client for OpenAlex)
- pandas (for data manipulation and CSV export)
"""
import pyalex
import pandas as pd

EMAIL = "niko.sirbiladze@gmail.com"  # Replace with your own

pyalex.config.email = EMAIL
pyalex.config.max_retries = 2

TOOLS_TO_PUBS = {
    "DeepLabCut": [
        # based on https://deeplabcut.github.io/DeepLabCut/docs/citation.html
        "https://doi.org/10.1038/s41593-018-0209-y",  # older DLC paper
        "https://doi.org/10.1038/s41596-019-0176-0",   # DLC for 3D
        "https://doi.org/10.1038/s41592-022-01443-0",  # DLC for multi-animal
        "https://doi.org/10.1038/s41467-024-48792-2",  # SuperAnimal models
    ],
    "SLEAP": [
        "https://doi.org/10.1038/s41592-018-0234-5",   # older LEAP paper
        "https://doi.org/10.1038/s41592-022-01426-1",  # main SLEAP paper
        "https://doi.org/10.1038/s41592-022-01495-2",  # correction
    ],
    "LightningPose": [
        "https://doi.org/10.1038/s41592-024-02319-1",  # main paper
        "https://doi.org/10.1101/2023.04.28.538703",  # preprint
    ],
    "DeepPoseKit": [
        "https://doi.org/10.7554/eLife.47994",  # main paper
        "https://doi.org/10.1101/620245",       # preprint
    ],
    "DANNCE": [
        "https://doi.org/10.1038/s41592-021-01106-6",  # main paper
    ],
    "TRex": [
        "https://doi.org/10.7554/eLife.64000",
    ],
    "idtracker": [
        "https://doi.org/10.1038/s41592-018-0295-5",
    ],
    "OpenPose": [
        "https://doi.org/10.48550/arXiv.1812.08008",  # main paper
        "https://doi.org/10.48550/arXiv.1704.07809",    # hand and face models
    ],
    "FastTrack": [
        "https://doi.org/10.1371/journal.pcbi.1008697",   # main paper
    ],
    "Anipose": [
        "https://doi.org/10.1016/j.celrep.2021.109730",  # main paper
        "https://doi.org/10.1101/2020.05.26.117325",  # preprint
    ],
    "FreiPose": [
        "https://doi.org/10.1101/2020.02.27.967620",  # preprint
    ],
    "DeepFly3D": [
        "https://doi.org/10.7554/eLife.48571",  # main paper
        "https://doi.org/10.1101/640375",  # preprint
    ],
    "OptiFlex": [
        "https://doi.org/10.3389/fncel.2021.621252",  # main paper
        "https://doi.org/10.1101/2020.04.04.025494",  # preprint
    ],
}


def fetch_citation_counts(tools_to_pubs):
    """Fetch citation counts for a list of tools from OpenAlex.

    Parameters
    ----------
    tools_to_pubs : dict
        A dictionary mapping each tool to a list of DOIs of the form
        (e.g. https://doi.org/10.1038/s41596-019-0176-0).

    Returns
    -------
    pandas.DataFrame
        A DataFrame containing the tool name and the number of citations
        aggregated across all publications related to that tool.

    """
    # Create a list of dictionaries to store the citation counts
    citations_per_tool: list[dict] = []

    # Iterate over each tool and its associated DOIs
    for tool, dois in tools_to_pubs.items():
        # Initialize the total citation count for the tool
        total_citation_count = 0

        # Ensure it's a list
        if isinstance(dois, str):
            dois = [dois]

        # Remove duplicates
        dois = list(set(dois))

        # Fetch Work object for each DOI and add its citation count
        for doi in dois:
            try:
                work = pyalex.Works()[doi]
                total_citation_count += work["cited_by_count"]
            except Exception as e:
                print(f"Error fetching data for tool {tool}, DOI {doi}: {e}")

        citations_per_tool.append({
            "tool": tool, "total_citation_count": total_citation_count,
        })

    df = pd.DataFrame(citations_per_tool)
    # Sort by citation count in descending order
    df = df.sort_values(
        by="total_citation_count", ascending=False, ignore_index=True
    )
    return df


if __name__ == "__main__":
    # Fetch citation counts for the tools
    citations_per_tool = fetch_citation_counts(TOOLS_TO_PUBS)
    print(citations_per_tool)
    # Save the results to a CSV file
    citations_per_tool.to_csv("citation_counts_per_tool.csv", index=False)
    print("Citation counts saved as citation_counts_per_tool.csv")
