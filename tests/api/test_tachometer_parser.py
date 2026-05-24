from src.modules.vehicle_hub.tachometer_parser import parse_tachometer_inspections


RESULT_HTML = """
<html>
  <body>
    <h2>Seznam prohlídek - VIN TMBJF73T2B9044629</h2>
    <table>
      <tbody>
        <tr>
          <td>15.05.2025</td>
          <td>STK</td>
          <td>CZ-3644-25-05-0162</td>
          <td>Evidenční kontrola</td>
          <td>416 588 km</td>
          <td>Bez závad</td>
          <td>Způsobilé</td>
          <td>0 závad</td>
        </tr>
        <tr>
          <td>22.04.2024</td>
          <td>EMISE</td>
          <td>CZ-3316-24-04-1239</td>
          <td>Pravidelná</td>
          <td>402 411</td>
          <td>Poznámka test</td>
          <td>Vyhověl</td>
          <td></td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""


def test_parse_tachometer_inspections_normalizes_core_fields() -> None:
    inspections = parse_tachometer_inspections(RESULT_HTML, "TMBJF73T2B9044629")

    assert len(inspections) == 2
    assert inspections[0].odometer_km == 416588
    assert inspections[0].inspection_type == "STK"
    assert inspections[0].inspection_kind == "Evidenční kontrola"
    assert inspections[0].protocol_number == "CZ-3644-25-05-0162"
    assert inspections[0].result_label == "Zpusobile"
    assert inspections[1].inspection_type == "SME"
    assert inspections[1].result_label == "Vyhovel"
    assert inspections[0].source_hash
