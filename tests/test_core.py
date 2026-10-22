from io import BytesIO
import json
import numpy as np
import pandas as pd
import pytest

from ingestion import load_data, sample_data
from quality import infer_columns, detect_issues, clean, boundary_metrics, numeric, outlier_mask


def test_sample_detects_and_preserves_source():
    df = sample_data()
    original = df.copy(deep=True)
    mapping = infer_columns(df)
    issues = detect_issues(df,mapping)
    assert {"Missing value","Duplicate Point ID","Elevation IQR outlier"} <= set(issues.Issue)
    result = clean(df,"Impute missing values","Elevation","Median")
    assert result.Elevation.isna().sum()==0
    pd.testing.assert_frame_equal(df,original)


def test_csv_ids_and_nulls():
    df,_ = load_data("points.csv",b"Point_ID;Easting;Northing;Elevation\n001;100;200;\n002;101;201;3")
    assert df.Point_ID.iloc[0]=="001"
    assert df.Elevation.isna().sum()==1
    assert len(df)==2


def test_json():
    df,_ = load_data("points.json",b'{"data":[{"id":"01","x":2,"meta":{"a":1}}]}')
    assert df.id.iloc[0]=="01"
    assert json.loads(df.meta.iloc[0])=={"a":1}


def test_geojson_preserves_rings():
    obj = {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"Parcel_ID":"A"},"geometry":{"type":"Polygon","coordinates":[[[0,0],[4,0],[4,4],[0,0]],[[1,1],[2,1],[2,2],[1,1]]]}}]}
    df,_ = load_data("parcel.geojson",json.dumps(obj).encode())
    assert len(df)==8
    assert df.Part_ID.nunique()==2
    assert df.Boundary_Flag.all()
    assert df.Parcel_ID.eq("A").all()


def test_xlsx_sheet_selection():
    buf = BytesIO()
    with pd.ExcelWriter(buf,engine="openpyxl") as writer:
        pd.DataFrame({"a":[1]}).to_excel(writer,sheet_name="one",index=False)
        pd.DataFrame({"b":[2,3]}).to_excel(writer,sheet_name="two",index=False)
    df,_ = load_data("test.xlsx",buf.getvalue(),"two")
    assert list(df.b)==[2,3]


def test_kml():
    xml = b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Boundary</name><Polygon><outerBoundaryIs><LinearRing><coordinates>1,2,3 4,5,6 7,8,9 1,2,3</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>'
    df,_ = load_data("parcel.kml",xml)
    assert len(df)==4 and df.Boundary_Flag.all()
    assert numeric(df.Elevation).iloc[0]==3


def test_gpx():
    df,_ = load_data("gps.gpx",b'<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg><trkpt lat="1.5" lon="103.7"><ele>8</ele><time>2026-01-01T00:00:00Z</time></trkpt></trkseg></trk></gpx>')
    assert float(df.Latitude.iloc[0])==1.5
    assert len(df)==1


def test_invalid_geometry_and_coordinates():
    df = pd.DataFrame({"x":["bad",np.inf,181],"y":[1,91,1],"geometry":["nope","POINT (0 0)","POLYGON ((0 0,2 2,0 2,2 0,0 0))"]})
    issues = detect_issues(df,infer_columns(df),geographic=True)
    assert (issues.Issue=="Invalid / empty geometry").sum()==2
    assert (issues.Issue=="Non-numeric / non-finite coordinate").sum()==2
    assert (issues.Issue=="Coordinate outside geographic range").sum()==2


def test_id_duplicate_keeps_missing_and_first():
    df = pd.DataFrame({"Point_ID":["A","A",None,None],"z":[1,2,3,4]})
    result = clean(df,"Drop duplicate Point IDs","Point_ID")
    assert len(result)==3
    assert result.z.iloc[0]==1


def test_cast_and_outliers():
    df = pd.DataFrame({"x":[1,2,3,4,5,100],"y":[1,2,3,4,5,6],"z":[1,2,3,4,5,100]})
    assert len(clean(df,"Remove spatial outliers",mapping=infer_columns(df)))==5
    assert len(clean(df,"Remove elevation outliers","z"))==5
    result = clean(pd.DataFrame({"a":["1","bad",None]}),"Cast column","a","Numeric")
    assert result.a.isna().sum()==2


def test_boundary_validity():
    assert boundary_metrics([[0,0],[3,0],[3,2],[0,2]])[1]==6
    assert boundary_metrics([[0,0],[2,2],[0,2],[2,0]])[1] is None


@pytest.mark.parametrize("name,body",[("bad.json",b"{"),("empty.csv",b"x,y\n"),("bad.gpx",b"<gpx>"),("bad.txt",b"anything")])
def test_bad_files(name,body):
    with pytest.raises(Exception):
        load_data(name,body)


def test_xml_entity_rejected():
    with pytest.raises(Exception):
        load_data("bad.gpx",b'<!DOCTYPE gpx [<!ENTITY test "boom">]><gpx>&test;</gpx>')


def test_no_numeric_and_empty():
    df = pd.DataFrame({"label":["a","b"]})
    assert detect_issues(df,infer_columns(df)).empty
    assert detect_issues(df.iloc[:0],infer_columns(df)).empty


def test_all_null_imputation_refused():
    with pytest.raises(ValueError):
        clean(pd.DataFrame({"z":[None,None]}),"Impute missing values","z","Median")


def test_nullable_integer_fractional_imputation():
    df = pd.DataFrame({"z": pd.Series([1, 2, None], dtype="Int64")})
    result = clean(df, "Impute missing values", "z", "Median")
    assert result.z.tolist() == [1, 2, 1.5]
    assert pd.isna(df.z.iloc[2])


def test_nullable_boolean_coordinate_does_not_crash_outlier_scan():
    values = pd.Series([True, False, True, False, None], dtype="boolean")
    assert not outlier_mask(values).any()


def test_categories_and_measurement_types():
    from quality import category_labels, numeric_columns
    df = pd.DataFrame({
        "flag": pd.Series([True, None], dtype="boolean"),
        "time": pd.to_datetime(["2026-10-22", None]),
        "z": [1., 2.],
    })
    assert category_labels(df.flag).tolist() == ["True", "(missing)"]
    assert numeric_columns(df) == ["z"]
