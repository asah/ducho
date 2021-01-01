#!/usr/bin/env python3

import os, sys, datetime, random, json, haversine

try:
    import ijson
except ImportError:
  print(f"ijson not installed - please run 'pip install ijson' and rerun.")
  sys.exit(1)

randseed=int(os.environ.get("RANDSEED", datetime.datetime.now().microsecond))
random.seed(randseed)

# mode to generate some data, run with GENERATE=1000 ./ducho.py to generate 1000 records
gen=int(os.environ.get("GENERATE", "0"))
if gen > 0:
  locs = []
  mints = int(os.environ.get("MINTS", "1294097317")) # approx dec 30, 2010
  maxts = int(os.environ.get("MAXTS", "2000000000")) # end of time
  if mints < 0:
    print(f"MINTS must be greater than zero.")
    sys.exit(1)
  if maxts <= mints:
    print(f"MINTS must be before MAXTS.")
    sys.exit(1)
  minlat = int(os.environ.get("MINLAT", "407226780")) # queensish
  maxlat = int(os.environ.get("MAXLAT", "407546850")) # new jerseyish
  minlon = int(os.environ.get("MINLON", "-742452120")) # staten island
  maxlon = int(os.environ.get("MAXLON", "-739111950")) # westchesterish
  for i in range(gen):
    ts = int(random.random() * (maxts - mints) + mints) * 1000
    lat = int(random.random() * (maxlat - minlat) + minlat)
    lon = int(random.random() * (maxlon - minlon) + minlon)
    locs.append({"timestampMs": ts, "latitudeE7": lat, "longitudeE7": lon})
  json.dump({"locations": locs}, sys.stdout)
  sys.exit(0)

max_tsdiff_secs = float(os.environ.get("MAX_TS_DIFF", "100"))  # secs
max_dist_km = float(os.environ.get("MAX_DIST_KM", "0.25"))  # km

if len(sys.argv) != 3:
  print(f"Usage: {sys.argv[0]} <takeout file1> <takeout file1>", file=sys.stderr)
  sys.exit(1)

def parseFile(filename):
  res = []
  items = ijson.items(open(filename), "locations.item")
  for item in items:
    if "longitudeE7" not in item or "latitudeE7" not in item or "timestampMs" not in item:
      continue
  
    # Fix overflows in Google Takeout data:
    # https://gis.stackexchange.com/questions/318918/latitude-and-longitude-values-in-google-takeout-location-history-data-sometimes
    if item["latitudeE7"] > 1800000000:
      item["latitudeE7"] = item["latitudeE7"] - 4294967296
    if item["longitudeE7"] > 1800000000:
      item["longitudeE7"] = item["longitudeE7"] - 4294967296
    ts = item["timestampMs"] / 1000
    res.append([ ts, item["latitudeE7"]/10000000.0, item["longitudeE7"]/10000000.0 ])
    #if len(res) % 100 == 0: print(".", end="", flush=True)
  #print("")
  return res
  
locs1=sorted(parseFile(sys.argv[1]), key=lambda rec: rec[0])
locs2=sorted(parseFile(sys.argv[2]), key=lambda rec: rec[0])

if len(locs1) == 0:
  print(f"didn't find any location-items in file1", file=sys.stderr)
  sys.exit(1)
if len(locs2) == 0:
  print(f"didn't find any location-items in file2", file=sys.stderr)
  sys.exit(1)

def avg(x,y):
  return (x+y)/2.0

i1 = i2 = 0
while i1 < len(locs1):
  loc1 = locs1[i1]
  loc2 = locs2[i2]
  ts1 = loc1[0]
  ts2 = loc2[0]
  # check time
  if abs(ts1 - ts2) < max_tsdiff_secs:
    #print(f"near in time: diff={abs(ts1 - ts2)} ts1={ts1} ts2={ts2}", end="")
    # check distance
    dist=haversine.haversine( loc1[1:], loc2[1:])
    #print(f"  dist={dist}")
    if dist < max_dist_km:
      print(f"colocated!  tsdiff: {abs(ts1 - ts2):3.0f} secs   dist: {dist:2.2f} km  "
            f"roughly {datetime.datetime.fromtimestamp(avg(ts1,ts2)).strftime('%Y-%m-%d %H:%M')} @ "
            f"{avg(loc1[1],loc2[1]):3.3f},{avg(loc1[2],loc2[2]):3.3f}")

  # advance the older of the counters
  #print(f"ts1={ts1} ts2={ts2} i1={i1} i2={i2}... ", end="", flush=True)
  if ts1 < ts2 or i2 == len(locs2)-1:
    #print(f"advancing i1.")
    i1 += 1
    continue
  i2 += 1
  #print(f"advancing i2.")


