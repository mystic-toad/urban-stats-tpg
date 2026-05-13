# ZIP Code Utility

This repo serves as a utility for reverse geocoding lat/lon pairs into zip codes in various formats. This is also a child project of [tpg_utils](https://github.com/mystic-toad/tpg-utils), a comprehensive photo metadata searching suite optimized for TPG, and features photo index integrations.

*This is still an early development-cycle application, expect issues. Please report any issues you find so they can be fixed.*

## Installation
- This feature uses several data processing and geographical dependencies. In your active virtual environment run:

```powershell
python -m pip install -r requirements.txt
```

## Usage
- The script defaults the census ZCTA archive filename to `cb_2018_us_zcta510_500k.zip`.
	This is the default and shouldn't be changed. In the event of an update or data change, the data source can be changed with  `--zipfile`.

### Search coordinates for ZIP (single or CSV of queries)

Search is now the default when `--zips` is not provided.

Single coordinate (positional lat lon):
```powershell
python zip_codes.py 38.044950193509585, -97.37610793857532 --out results.csv
```

CSV input (headers: `name,lat,lon` or at minimum `lat,lon`):
```powershell
python zip_codes.py --csv queries.csv --out results.csv
```

### Assign photos to ZIPs (priority list)

This mode runs when you pass `--zips` and an existing `photofind` index. It reads the prioritized ZIP list and assigns photos to the first ZIP polygon that contains them (each photo is assigned at most once).

```powershell
python zip_codes.py --index index.pkl --zips sources.csv --out zip_photos.csv
```



Outputs
- Assign mode (`--zips` provided):
	- File: `zip_photos.csv`
	- Columns: `zip,photo_file,photo_lat,photo_lon`
	- Description: one row per photo assigned to a ZIP. Rows list the ZIP value, the photo file path, and the photo's lat/lon. Photos are assigned to the first matching ZIP (each photo appears at most once).

- Search mode (default when `--zips` omitted):
	- File: `results.csv`
	- Columns: `query_name,query_lat,query_lon,zip`
	- Description: one row per search query. `query_name` is taken from the CSV `name` column when present (empty otherwise). `zip` will be empty when no containing ZCTA polygon is found.

Sample commands
```powershell
# single coordinate search (positional lat lon)
python zip_codes.py 40.12345 -105.12345 --out search_results.csv

# CSV search (queries.csv must have headers lat,lon and optional name)
python zip_codes.py --csv queries.csv --out search_results.csv

# Assign photos to prioritized ZIP list (my_zips.csv). Limit total ZIPs processed to 15 (default):
python zip_codes.py --index index.pkl --zips my_zips.csv --out zip_photos.csv

# Assign but only process the top 10 ZIPs from the list (stop after 10 ZIPs with matches):
python zip_codes.py --index index.pkl --zips my_zips.csv --out zip_photos.csv -n 10
```

Notes
- The script expects the census shapefile archive (default: `cb_2018_us_zcta510_500k.zip`). If it cannot read the archive, unzip it and point `--zipfile` to the `.shp` file.
- For assign mode you must provide a `photofind` index (the default `index.pkl` is used when `--index` is omitted).
- The script will try to detect the ZIP field in the shapefile (common field names: `ZCTA5CE10`, `GEOID10`, etc.). If detection fails pass `--shp-zip-field` with the proper column name.

Examples
- Find ZIPs for a list of coordinates and open the CSV in Excel.
 - Assign photos to a prioritized list of ZIPs (top-of-file wins). Each photo will be assigned to the first matching ZIP and will not be duplicated across later ZIPs.

## License & Disclaimer
- This is a small helper intended to plug into the existing photofind workflow. Review the code and run on a test directory first. The author accepts no responsibility for data loss.
- US Census Data used in this project, under appropriate licenses.
- ZIP Code trademark owned by United States Postal Office, which has no affiliation and does not endorse this project.
