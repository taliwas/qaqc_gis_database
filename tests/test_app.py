from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1]/"app.py")


def test_app_sample_and_cleaning_undo_reset():
    at = AppTest.from_file(APP,default_timeout=60).run()
    assert not at.exception
    assert len(at.tabs)==3
    assert len(at.get("plotly_chart"))==11
    at.selectbox(key="clean_action").set_value("Drop duplicate Point IDs").run()
    next(b for b in at.button if b.label=="Preview fix").click().run()
    assert not at.exception
    next(b for b in at.button if b.label=="Apply this fix").click().run()
    assert len(at.session_state["working"])==239
    next(b for b in at.button if b.label=="Undo last fix").click().run()
    assert len(at.session_state["working"])==240
    next(b for b in at.button if "Reset All" in b.label).click().run()
    assert not at.exception
    assert at.session_state["fixed"]==0


def test_app_generic_categorical():
    at = AppTest.from_file(APP,default_timeout=60)
    at.session_state["working"] = pd.DataFrame({"Label":["A","B"]})
    at.session_state["raw"] = pd.DataFrame({"Label":["A","B"]})
    for k,v in {"name":"generic","size":0,"note":"","audit":[],"history":[],"fixed":0,"preview":None,"revision":0}.items():
        at.session_state[k]=v
    at.run()
    assert not at.exception


def test_app_empty_working_copy():
    at = AppTest.from_file(APP,default_timeout=60).run()
    at.session_state["working"] = at.session_state["working"].iloc[:0]
    at.run()
    assert not at.exception


def test_nullable_boolean_category_and_header_reset():
    at = AppTest.from_file(APP, default_timeout=60).run()
    frame = at.session_state["working"].copy()
    frame["Boundary_Flag"] = frame["Boundary_Flag"].astype("boolean")
    frame.loc[5, "Boundary_Flag"] = pd.NA
    at.session_state["working"] = frame
    at.selectbox(key="dash_category").set_value("Boundary_Flag").run()
    assert not at.exception
    at.selectbox(key="dash_color").set_value("Boundary_Flag").run()
    assert not at.exception
    at.button(key="header_reset").click().run()
    assert not at.exception
    assert not at.session_state["working"].Boundary_Flag.isna().any()
