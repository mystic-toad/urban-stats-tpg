#!/usr/bin/env python3
"""
zip_codes.py - assign photos from a photofind index to census ZCTA (ZIP) polygons

Usage:
    python zip_codes.py --index index.pkl --zips zips.csv [--out zip_photos.csv]

Dependencies:
    python -m pip -r requirements.txt

The script hardcodes the expected census ZCTA archive filename to
`cb_2018_us_zcta510_500k.zip`. If your shapefile is named differently, pass
it with `--zipfile`.

"""
import sys
import pickle
import argparse
import csv
from pathlib import Path

try:
    import geopandas as gpd
    from shapely.geometry import Point
except Exception as e:
    print("Missing dependency: geopandas (and shapely).\nInstall with: python -m pip install geopandas shapely fiona")
    sys.exit(1)


def _collect_photos(node):
    if node is None:
        return []
    left = _collect_photos(node.get("left"))
    right = _collect_photos(node.get("right"))
    return [*left, node["photo"], *right]

# pulls zips from csv file (should be format ambiguous)
def read_zip_list(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"ZIP list not found: {path}")

    zips = []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        # find header row zip index
        if headers and any(h.strip().isalpha() for h in headers):
            # treat first row as header
            f.seek(0)
            dreader = csv.DictReader(f)
            # try common header names
            keys = [k for k in dreader.fieldnames if k and k.strip().lower() in ("zip", "zip codes", "zip code", "zips", "zipcode", "zipcodes", "postcode", "postalcode", "postal_code", "postal codes")]
            if keys:
                key = keys[0]
                for row in dreader:
                    val = row.get(key)
                    if val:
                        zips.append(val.strip())
                return zips
            # fallback: take first column
            f.seek(0)
            for row in csv.reader(f):
                if row:
                    zips.append(row[0].strip())
            return zips

        # no obvious header so treat every row as a single ZIP value
        if headers:
            zips.append(headers[0].strip())
        for row in reader:
            if row:
                zips.append(row[0].strip())

    return zips


def find_shp_zip_field(gdf, provided=None):
    if provided and provided in gdf.columns:
        return provided
    candidates = [
        "ZCTA5CE10", "ZCTA5CE", "ZCTA5", "ZCTA5CE20", "GEOID10", "ZCTA5CE00"
    ]
    for c in candidates:
        if c in gdf.columns:
            return c
    # fallback: try any column that looks like all-numeric or all-length-5 strings
    for c in gdf.columns:
        try:
            sample = gdf[c].dropna().astype(str).iloc[0]
            if len(sample) >= 3:
                return c
        except Exception:
            continue
    return None


def main():
    p = argparse.ArgumentParser(prog="zip_codes",
                                description="Assign photos from an index into ZIP polygons or find ZIP for coordinates")
    p.add_argument("--index", default="index.pkl",
                   help="photofind index (pickle) - required for assign mode")
    p.add_argument("--zipfile", default="cb_2018_us_zcta510_500k.zip",
                   help="Path to census ZCTA shapefile ZIP archive (default: cb_2018_us_zcta510_500k.zip)")
    p.add_argument("--shp-zip-field", default=None, help="(optional) shapefile column containing ZIP code")

    # assign mode inputs
    p.add_argument("--zips", help="CSV file with ZIPs in priority order (top first) - assign mode")
    p.add_argument("--out", default="zip_photos.csv", help="Output CSV mapping ZIP -> photo files (assign) or query results (search)")
    p.add_argument("-n", "--n", type=int, default=15,
                   help="Max number of ZIPs to process (default: 15)")

    # positional search coordinates (optional). Example: `python zip_codes.py 40.1 -105.2`
    p.add_argument("lat", type=float, nargs="?", help="Latitude for single search query (positional)")
    p.add_argument("lon", type=float, nargs="?", help="Longitude for single search query (positional)")
    p.add_argument("--csv", metavar="FILE", help="CSV file with name,lat,lon rows to search (search mode)")

    args = p.parse_args()

    # load shapes
    shp_path = Path(args.zipfile)
    if not shp_path.exists():
        print(f"Shapefile zip not found: {shp_path}")
        sys.exit(1)

    try:
        zips_gdf = gpd.read_file(str(shp_path))
    except Exception as e:
        print("Failed to read shapefile zip with geopandas:", e)
        print("Try unzipping the archive and passing the .shp file directly.")
        sys.exit(1)

    # Ensure same coord system
    try:
        if zips_gdf.crs and zips_gdf.crs.to_string() != "EPSG:4326":
            zips_gdf = zips_gdf.to_crs("EPSG:4326")
    except Exception:
        pass

    shp_field = find_shp_zip_field(zips_gdf, args.shp_zip_field)
    if not shp_field:
        print("Could not detect ZIP field in shapefile. Available columns:")
        print(list(zips_gdf.columns))
        sys.exit(1)

    # search mode (default)
    if not args.zips:
        # load queries
        queries = []
        if args.csv:
            csv_path = Path(args.csv)
            if not csv_path.exists():
                print(f"CSV not found: {args.csv}")
                sys.exit(1)
            with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    print(f"CSV is empty: {args.csv}")
                    sys.exit(1)
                normalized_fields = {field.strip().lower() for field in reader.fieldnames if field}
                required_fields = {"lat", "lon"}
                if not required_fields.issubset(normalized_fields):
                    print("CSV must include headers for lat and lon, optionally name.")
                    sys.exit(1)
                for row_num, row in enumerate(reader, start=2):
                    normalized = {
                        (key.strip().lower() if key else ""): (value.strip() if isinstance(value, str) else value)
                        for key, value in row.items()
                    }
                    if not normalized.get("lat") or not normalized.get("lon"):
                        print(f"Skipping row {row_num} in {args.csv}: missing lat or lon")
                        continue
                    try:
                        lat = float(normalized["lat"])
                        lon = float(normalized["lon"])
                    except ValueError:
                        print(f"Skipping row {row_num} in {args.csv}: invalid lat/lon")
                        continue
                    name = normalized.get("name") or f"row_{len(queries) + 1}"
                    queries.append({"name": name, "lat": lat, "lon": lon})
        else:
            if args.lat is None or args.lon is None:
                print("Search requires either --lat and --lon or --csv FILE.")
                sys.exit(1)
            queries = [{"name": None, "lat": args.lat, "lon": args.lon}]

        if not queries:
            print("No valid search queries.")
            sys.exit(1)

        # format results, calculate edge cases
        results = []
        for q in queries:
            pt = Point(q["lon"], q["lat"])
            zipval = None

            # limits candidates
            try:
                sidx = zips_gdf.sindex
            except Exception:
                sidx = None

            if sidx is not None:
                bbox_idx = list(sidx.intersection(pt.bounds))
                candidates = zips_gdf.iloc[bbox_idx]
            else:
                candidates = zips_gdf

            # strict contains
            containing = candidates[candidates.geometry.contains(pt)]

            # intersects (covers boundary cases)
            if containing.empty:
                containing = candidates[candidates.geometry.intersects(pt)]

            # tiny buffer around point to catch numeric/boundary issues
            if containing.empty:
                try:
                    buff = pt.buffer(1e-9)
                    containing = candidates[candidates.geometry.intersects(buff)]
                except Exception:
                    pass

            if not containing.empty:
                # take first matching feature
                zipval = str(containing.iloc[0][shp_field])

            results.append({"name": q.get("name"), "lat": q["lat"], "lon": q["lon"], "zip": zipval})

        # write output csv in simple query format
        out_path = Path(args.out)
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["query_name", "query_lat", "query_lon", "zip"])
            for r in results:
                writer.writerow([r.get("name") or "", f"{r['lat']:.6f}", f"{r['lon']:.6f}", r.get("zip") or ""])

        print(f"Wrote {len(results)} query results to {out_path}")
        return

    # otherwise run assign mode (requires index and zips CSV)
    if not args.zips:
        print("Assign mode requires --zips CSV file with ZIPs in priority order.")
        sys.exit(1)

    index_path = Path(args.index)
    if not index_path.exists():
        print(f"Index not found: {index_path}. Run photofind_alpha index first.")
        sys.exit(1)

    with open(index_path, "rb") as f:
        index = pickle.load(f)

    photos = _collect_photos(index.get("tree"))
    if not photos:
        print("Index contains no photos.")
        sys.exit(1)

    # assembly geodataframe for photos
    pts = [Point(p["lon"], p["lat"]) for p in photos]
    pg = gpd.GeoDataFrame(photos, geometry=pts, crs="EPSG:4326")

    # read thru zip list
    zip_list = read_zip_list(args.zips)
    if not zip_list:
        print(f"No ZIPs found in {args.zips}")
        sys.exit(1)

    # update unassigned pics index
    unassigned_idx = set(range(len(pg)))

    out_rows = []

    zips_found = 0
    for z in zip_list:
        # match shapefile rows where the field equals the requested zip (string compare)
        mask = zips_gdf[shp_field].astype(str) == str(z)
        if not mask.any():
            # try padding/stripping leading zeros
            mask = zips_gdf[shp_field].astype(str).str.zfill(5) == str(z).zfill(5)

        if not mask.any():
            print(f"Warning: ZIP {z} not found in shapefile.")
            continue

        try:
            polygon = zips_gdf[mask].geometry.union_all()
        except AttributeError:
            polygon = zips_gdf[mask].geometry.unary_union
        if polygon is None:
            continue

        # find photos within polygon among unassigned
        matches = []
        if unassigned_idx:
            subset = pg.loc[list(unassigned_idx)]
            try:
                mask = subset.geometry.within(polygon)
            except Exception:
                # fallback to slower apply if underlying geometry op fails
                from shapely.prepared import prep
                prep_poly = prep(polygon)
                mask = subset.geometry.apply(lambda g: prep_poly.contains(g))

            # original row labels
            matches = list(subset.index[mask].tolist())

        # for if zip has no photos
        if not matches:
            continue

        # add all matching photos for this zip
        for mi in matches:
            row = pg.loc[mi]
            out_rows.append((str(z), row["path"], f"{row['lat']:.6f}", f"{row['lon']:.6f}"))
            # remove previously assigned photos (i know this is inefficient)
            unassigned_idx.discard(mi)

        zips_found += 1
        if args.n and zips_found >= args.n:
            print(f"Reached requested max ZIPs to process: {args.n}")
            break

    # write output csv
    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["zip", "photo_file", "photo_lat", "photo_lon"])
        for r in out_rows:
            writer.writerow(r)

    print(f"Wrote {len(out_rows)} photo assignments to {out_path}")


if __name__ == "__main__":
    main()
