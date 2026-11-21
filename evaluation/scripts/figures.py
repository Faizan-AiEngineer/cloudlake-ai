import argparse
import csv
from pathlib import Path

from reportlab.graphics import renderSVG
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib.colors import HexColor


def records(path):
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def chart(title, categories, values, units, destination):
    drawing = Drawing(620, 200)
    drawing.add(String(26, 173, title, fontName="Helvetica-Bold", fontSize=16, fillColor=HexColor("#16304b")))
    drawing.add(String(26, 151, units, fontSize=9, fillColor=HexColor("#475d75")))
    figure = HorizontalBarChart()
    figure.x, figure.y, figure.width, figure.height = 155, 35, 410, 104
    figure.data = [values]
    figure.categoryAxis.categoryNames = categories
    figure.categoryAxis.labels.fontSize = 10
    figure.valueAxis.labels.fontSize = 8
    figure.valueAxis.valueMin = 0
    figure.valueAxis.labelTextFormat = lambda value: f"{value:,.0f}"
    figure.bars[0].fillColor = HexColor("#317bb9")
    figure.bars[0].strokeColor = None
    drawing.add(figure)
    renderSVG.drawToFile(drawing, str(destination))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("evaluation/results"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/reports/figures"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    measured = records(args.results / "batch_performance.csv") + records(args.results / "scale_performance.csv")
    runs = [row for row in measured if row["status"] == "successful"]
    chart("Successful batch throughput", [row["profile"].title() for row in runs],
          [float(row["throughput_rows_per_second"]) for row in runs], "Evaluated rows per second",
          args.output / "batch-throughput.svg")
    storage = records(args.results / "storage_efficiency.csv")
    chart("Equivalent order data storage", [row["format"].upper() for row in storage],
          [int(row["bytes"]) for row in storage], f"Bytes for {int(storage[0]['rows']):,} logical records",
          args.output / "storage-efficiency.svg")


if __name__ == "__main__":
    main()
