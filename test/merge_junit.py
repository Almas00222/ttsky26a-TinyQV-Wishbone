#!/usr/bin/env python3
import sys
import xml.etree.ElementTree as ET


COUNT_ATTRS = ("tests", "failures", "errors", "skipped")
TIME_ATTRS = ("time",)


def parse_attr(element, name, cast):
    raw = element.get(name)
    if raw is None or raw == "":
        return cast(0)
    return cast(raw)


def iter_suites(root):
    if root.tag == "testsuite":
        yield root
    elif root.tag == "testsuites":
        yield from root.findall("testsuite")
    else:
        raise ValueError(f"Unsupported JUnit root tag {root.tag!r}")


def main(argv):
    if len(argv) < 2:
        raise SystemExit("usage: merge_junit.py <results1.xml> <results2.xml> ...")

    merged = ET.Element("testsuites")
    counts = {name: 0 for name in COUNT_ATTRS}
    times = {name: 0.0 for name in TIME_ATTRS}

    for path in argv[1:]:
        root = ET.parse(path).getroot()
        for suite in iter_suites(root):
            merged.append(suite)
            for name in COUNT_ATTRS:
                counts[name] += parse_attr(suite, name, int)
            for name in TIME_ATTRS:
                times[name] += parse_attr(suite, name, float)

    for name, value in counts.items():
        merged.set(name, str(value))
    for name, value in times.items():
        merged.set(name, f"{value:.6f}")

    ET.ElementTree(merged).write(sys.stdout.buffer, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main(sys.argv)
