import 'dart:ui' show PointMode;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/session.dart';
import '../../../models/figure.dart';

/// Figures chargées une fois par lancement de l'application (elles changent rarement).
final figureProvider = FutureProvider.family<Figure, String>(
  (ref, id) => ref.watch(apiProvider).figure(id),
);

const _areaColors = [
  Color(0xFFF6D8C8),
  Color(0xFFCFE3F6),
  Color(0xFFD5EDCF),
  Color(0xFFF7E6B0),
  Color(0xFFE3D5F4),
  Color(0xFFF4D0DE),
  Color(0xFFCDEDE8),
  Color(0xFFEADBC8),
];
const _outline = Color(0xFF5B5448);

/// Dessin d'une figure. [colors] remplace la couleur de zones ; [plain] : coloriage, surfaces
/// blanches. Toucher une zone appelle [onTapZone]. Pincer pour zoomer.
class FigureCanvas extends StatelessWidget {
  const FigureCanvas({
    required this.figure,
    this.colors = const {},
    this.plain = false,
    this.onTapZone,
    super.key,
  });

  final Figure figure;
  final Map<String, Color> colors;
  final bool plain;
  final ValueChanged<FigureZone>? onTapZone;

  @override
  Widget build(BuildContext context) => ClipRRect(
    borderRadius: BorderRadius.circular(12),
    child: AspectRatio(
      aspectRatio: figure.size.width / figure.size.height,
      child: InteractiveViewer(
        maxScale: 6,
        child: LayoutBuilder(
          builder: (context, box) {
            final scale = box.maxWidth / figure.size.width;
            return GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTapUp: onTapZone == null
                  ? null
                  : (details) {
                      final zone = figure.hit(details.localPosition / scale, 14 / scale);
                      if (zone != null) onTapZone!(zone);
                    },
              child: CustomPaint(
                key: const ValueKey('figure-canvas'),
                size: box.biggest,
                painter: _FigurePainter(figure, colors, plain: plain),
              ),
            );
          },
        ),
      ),
    ),
  );
}

class _FigurePainter extends CustomPainter {
  _FigurePainter(this.figure, this.colors, {required this.plain});

  final Figure figure;
  final Map<String, Color> colors;
  final bool plain;

  @override
  void paint(Canvas canvas, Size size) {
    final scale = size.width / figure.size.width;
    canvas.save();
    canvas.scale(scale);
    final hairline = 1.2 / scale;
    for (final d in figure.decor) {
      for (final path in d.paths) {
        if (!d.line && d.fill != null) canvas.drawPath(path, Paint()..color = d.fill!);
        if (d.stroke != null) {
          canvas.drawPath(
            path,
            Paint()
              ..style = PaintingStyle.stroke
              ..strokeWidth = d.width
              ..color = d.stroke!,
          );
        }
      }
    }
    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = hairline
      ..color = _outline;
    for (final (index, zone) in figure.zones.indexed) {
      final colour =
          colors[zone.id] ??
          (plain ? Colors.white : zone.fill ?? _areaColors[index % _areaColors.length]);
      switch (zone.kind) {
        case ZoneKind.area:
          for (final path in zone.paths) {
            canvas
              ..drawPath(path, Paint()..color = colour)
              ..drawPath(path, stroke);
          }
          if (zone.marker case final Offset centre) {
            canvas
              ..drawCircle(centre, zone.markerRadius, Paint()..color = colour)
              ..drawCircle(centre, zone.markerRadius, stroke);
          }
        case ZoneKind.line:
          final paint = Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = (colors.containsKey(zone.id) ? 6 : 3.5) / scale
            ..strokeCap = StrokeCap.round
            ..strokeJoin = StrokeJoin.round
            ..color = colors[zone.id] ?? zone.fill ?? const Color(0xFF3D7CC9);
          for (final line in zone.lines) {
            canvas.drawPoints(PointMode.polygon, line, paint);
          }
        case ZoneKind.point:
          for (final path in zone.paths) {
            canvas
              ..drawPath(path, Paint()..color = colors[zone.id] ?? Colors.white)
              ..drawPath(path, stroke..strokeWidth = 2 / scale);
          }
          stroke.strokeWidth = hairline;
      }
    }
    for (final label in figure.labels) {
      final text = TextPainter(
        text: TextSpan(
          text: label.text,
          style: TextStyle(fontSize: label.size, color: Colors.black87),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      text.paint(canvas, label.position - Offset(text.width / 2, text.height / 2));
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_FigurePainter old) =>
      old.figure != figure || old.colors != colors || old.plain != plain;
}

/// Charge la figure [id] puis la dessine avec [builder], avec ses sources (licences des cartes) ;
/// message et « Réessayer » si le réseau manque.
class FigureLoader extends ConsumerWidget {
  const FigureLoader({required this.id, required this.builder, super.key});

  final String id;
  final Widget Function(Figure figure) builder;

  @override
  Widget build(BuildContext context, WidgetRef ref) => ref
      .watch(figureProvider(id))
      .when(
        data: (figure) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            builder(figure),
            if (figure.credits.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  figure.credits,
                  style: const TextStyle(fontSize: 11, color: Colors.black45),
                ),
              ),
          ],
        ),
        loading: () => const Padding(
          padding: EdgeInsets.all(32),
          child: Center(child: CircularProgressIndicator()),
        ),
        error: (_, _) => Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              const Text('Le dessin n\'a pas pu être chargé.', style: TextStyle(fontSize: 17)),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: () => ref.invalidate(figureProvider(id)),
                child: const Text('Réessayer'),
              ),
            ],
          ),
        ),
      );
}
