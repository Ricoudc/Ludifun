import 'dart:ui';

import 'account.dart';

/// Figure d'une carte ou d'un schéma (étape 22), servie par `GET /v1/figures/{id}`.
///
/// Unités de dessin : `width` × `height`, y vers le bas. Chaque polygone est une liste
/// d'anneaux (le premier extérieur, les suivants des trous).
class Figure {
  Figure({
    required this.id,
    required this.title,
    required this.credits,
    required this.size,
    required this.decor,
    required this.zones,
    required this.labels,
  });

  factory Figure.fromJson(Json json) => Figure(
    id: json['id'] as String,
    title: json['title'] as String,
    credits: json['credits'] as String? ?? '',
    size: Size((json['width'] as num).toDouble(), (json['height'] as num).toDouble()),
    decor: [for (final d in json['decor'] as List<dynamic>) FigureDecor.fromJson(d as Json)],
    zones: [for (final z in json['zones'] as List<dynamic>) FigureZone.fromJson(z as Json)],
    labels: [
      for (final l in json['labels'] as List<dynamic>? ?? []) FigureLabel.fromJson(l as Json),
    ],
  );

  final String id;
  final String title;
  final String credits;
  final Size size;
  final List<FigureDecor> decor;
  final List<FigureZone> zones;
  final List<FigureLabel> labels;

  FigureZone? zone(String id) => zones.where((z) => z.id == id).firstOrNull;

  /// La zone touchée en [point] (unités de dessin) ; [tolerance] autour des traits et des points.
  FigureZone? hit(Offset point, double tolerance) {
    FigureZone? nearest;
    var best = double.infinity;
    for (final zone in zones) {
      final distance = zone.distanceTo(point);
      if (distance != null && distance <= tolerance && distance < best) {
        nearest = zone;
        best = distance;
      }
    }
    if (nearest != null) return nearest;
    // Surfaces : la dernière dessinée est au-dessus.
    for (final zone in zones.reversed) {
      if (zone.kind == ZoneKind.area && zone.paths.any((p) => p.contains(point))) return zone;
    }
    return null;
  }
}

enum ZoneKind { area, line, point }

List<Path> _polygons(Object? shapes, {required bool closed}) => [
  for (final polygon in shapes as List<dynamic>)
    Path()
      ..fillType = PathFillType.evenOdd
      ..addPolygonsFrom(polygon as List<dynamic>, closed: closed),
];

extension on Path {
  void addPolygonsFrom(List<dynamic> rings, {required bool closed}) {
    for (final ring in rings) {
      addPolygon(_points(ring as List<dynamic>), closed);
    }
  }
}

List<Offset> _points(List<dynamic> flat) => [
  for (var i = 0; i + 1 < flat.length; i += 2)
    Offset((flat[i] as num).toDouble(), (flat[i + 1] as num).toDouble()),
];

Color? parseColor(Object? hex) {
  if (hex is! String || hex.length != 7 || !hex.startsWith('#')) return null;
  final value = int.tryParse(hex.substring(1), radix: 16);
  return value == null ? null : Color(0xFF000000 | value);
}

class FigureZone {
  FigureZone({
    required this.id,
    required this.name,
    required this.kind,
    required this.paths,
    required this.lines,
    this.fill,
    this.marker,
    this.markerRadius = 0,
  });

  factory FigureZone.fromJson(Json json) {
    final kind = ZoneKind.values.byName(json['kind'] as String);
    final marker = json['marker'] as List<dynamic>?;
    final shapes = json['shapes'] as List<dynamic>;
    return FigureZone(
      id: json['id'] as String,
      name: json['name'] as String,
      kind: kind,
      paths: kind == ZoneKind.line ? const [] : _polygons(shapes, closed: true),
      lines: kind == ZoneKind.line
          ? [
              for (final polygon in shapes)
                for (final ring in polygon as List<dynamic>) _points(ring as List<dynamic>),
            ]
          : const [],
      fill: parseColor(json['fill']),
      marker: marker == null
          ? null
          : Offset((marker[0] as num).toDouble(), (marker[1] as num).toDouble()),
      markerRadius: marker == null ? 0 : (marker[2] as num).toDouble(),
    );
  }

  final String id;
  final String name;
  final ZoneKind kind;
  final List<Path> paths; // surfaces et points
  final List<List<Offset>> lines; // fleuves, rivières
  final Color? fill;

  /// Repère rond d'une zone trop petite pour être touchée (micro-État, îlot).
  final Offset? marker;
  final double markerRadius;

  /// Distance à un trait, à un point ou au repère ; null pour une surface ordinaire.
  double? distanceTo(Offset point) {
    switch (kind) {
      case ZoneKind.line:
        var best = double.infinity;
        for (final line in lines) {
          for (var i = 0; i + 1 < line.length; i++) {
            final d = _segmentDistance(point, line[i], line[i + 1]);
            if (d < best) best = d;
          }
        }
        return best;
      case ZoneKind.point:
        final bounds = paths.first.getBounds();
        return (point - bounds.center).distance - bounds.width / 2;
      case ZoneKind.area:
        final m = marker;
        return m == null ? null : (point - m).distance - markerRadius;
    }
  }
}

double _segmentDistance(Offset p, Offset a, Offset b) {
  final ab = b - a;
  final length2 = ab.dx * ab.dx + ab.dy * ab.dy;
  if (length2 == 0) return (p - a).distance;
  final ap = p - a;
  final t = ((ap.dx * ab.dx + ap.dy * ab.dy) / length2).clamp(0.0, 1.0);
  return (p - (a + ab * t)).distance;
}

class FigureDecor {
  FigureDecor({required this.line, required this.paths, this.fill, this.stroke, this.width = 1});

  factory FigureDecor.fromJson(Json json) {
    final line = json['kind'] == 'line';
    return FigureDecor(
      line: line,
      paths: _polygons(json['shapes'], closed: !line),
      fill: parseColor(json['fill']),
      stroke: parseColor(json['stroke']),
      width: (json['width'] as num?)?.toDouble() ?? 1,
    );
  }

  final bool line;
  final List<Path> paths;
  final Color? fill;
  final Color? stroke;
  final double width;
}

class FigureLabel {
  FigureLabel({required this.text, required this.position, required this.size});

  factory FigureLabel.fromJson(Json json) => FigureLabel(
    text: json['text'] as String,
    position: Offset((json['x'] as num).toDouble(), (json['y'] as num).toDouble()),
    size: (json['size'] as num).toDouble(),
  );

  final String text;
  final Offset position;
  final double size;
}
