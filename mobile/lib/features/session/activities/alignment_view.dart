import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Points alignés (géométrie) : la figure est dessinée ici à partir des coordonnées envoyées par
/// le serveur (feuille de 24 × 14 carreaux).
///
/// - `{prompt, task:"yes_no", points:[{id,x,y,color}], choices}` → `{choice_id}` ;
/// - `{prompt, task:"select", shape:"dot"|"nail", points, count?}` → `{selected:[id…]}` :
///   l'enfant touche les points (un second toucher les retire), puis « Valider ».
class AlignmentView extends StatefulWidget {
  const AlignmentView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<AlignmentView> createState() => _AlignmentViewState();
}

/// Un point de la figure.
typedef FigurePoint = ({String id, double x, double y, bool blue});

const _sheetWidth = 24.0;
const _sheetHeight = 14.0;

List<FigurePoint> pointsOf(Object? list) => [
  for (final p in list as List<dynamic>)
    (
      id: (p as Json)['id'] as String,
      x: (p['x'] as num).toDouble(),
      y: (p['y'] as num).toDouble(),
      blue: p['color'] == 'blue',
    ),
];

class _AlignmentViewState extends State<AlignmentView> {
  late final List<FigurePoint> _points = pointsOf(widget.payload['points']);
  final _selected = <String>{};
  bool _sent = false;

  bool get _yesNo => widget.payload['task'] == 'yes_no';
  int? get _count => (widget.payload['count'] as num?)?.toInt();

  void _toggle(String id) {
    if (_sent || _yesNo) return;
    if (_points.firstWhere((p) => p.id == id).blue) return; // les points bleus sont donnés
    setState(() => _selected.contains(id) ? _selected.remove(id) : _selected.add(id));
  }

  void _send(Map<String, Object?> response) {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit(response);
  }

  @override
  Widget build(BuildContext context) {
    final count = _count;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(widget.payload['prompt'] as String, label: ActivityInstruction.of(context)),
        const SizedBox(height: 12),
        AlignmentFigure(
          points: _points,
          selected: _selected,
          nails: widget.payload['shape'] == 'nail',
          onTap: _sent || _yesNo ? null : _toggle,
        ),
        const SizedBox(height: 16),
        if (_yesNo)
          for (final (i, choice) in choicesOf(widget.payload['choices']).indexed) ...[
            AnswerButton(
              label: choice.text,
              color: i == 0 ? LudiColors.primary : LudiColors.accent,
              onPressed: () => _send({'choice_id': choice.id}),
            ),
            const SizedBox(height: 12),
          ]
        else ...[
          Text(
            count == null
                ? 'Points touchés : ${_selected.length}'
                : 'Points touchés : ${_selected.length} / $count',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: _sent || _selected.isEmpty
                ? null
                : () => _send({'selected': _selected.toList()..sort()}),
            child: const Text('Valider'),
          ),
        ],
      ],
    );
  }
}

/// La feuille : les points (ou des clous), leur lettre, et le choix de l'enfant entouré.
class AlignmentFigure extends StatelessWidget {
  const AlignmentFigure({
    required this.points,
    required this.selected,
    this.nails = false,
    this.onTap,
    super.key,
  });

  final List<FigurePoint> points;
  final Set<String> selected;
  final bool nails;
  final void Function(String id)? onTap;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: (_sheetWidth + 2) / (_sheetHeight + 2),
      child: LayoutBuilder(
        builder: (context, box) {
          final scale = box.maxWidth / (_sheetWidth + 2);
          Offset at(FigurePoint p) => Offset((p.x + 1) * scale, (p.y + 1) * scale);
          return GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapUp: onTap == null
                ? null
                : (details) {
                    // Le point le plus proche du doigt, s'il est assez près (doigt d'enfant).
                    final nearest = points.reduce(
                      (a, b) =>
                          (at(a) - details.localPosition).distance <=
                              (at(b) - details.localPosition).distance
                          ? a
                          : b,
                    );
                    if ((at(nearest) - details.localPosition).distance <= scale * 1.1) {
                      onTap!(nearest.id);
                    }
                  },
            child: Container(
              decoration: BoxDecoration(
                color: Colors.white,
                border: Border.all(color: Colors.black26),
                borderRadius: BorderRadius.circular(12),
              ),
              child: CustomPaint(
                painter: _SheetPainter(
                  points,
                  selected,
                  nails,
                  scale,
                  DefaultTextStyle.of(context).style,
                ),
                size: Size.infinite,
              ),
            ),
          );
        },
      ),
    );
  }
}

class _SheetPainter extends CustomPainter {
  _SheetPainter(this.points, this.selected, this.nails, this.scale, this.font);

  final List<FigurePoint> points;
  final Set<String> selected;
  final bool nails;
  final double scale;
  final TextStyle font; // la police de l'écran, pour les lettres des points

  @override
  void paint(Canvas canvas, Size size) {
    final dot = math.max(4.0, scale * 0.28);
    for (final p in points) {
      final center = Offset((p.x + 1) * scale, (p.y + 1) * scale);
      final color = p.blue ? const Color(0xFF1E88E5) : Colors.black87;
      if (nails) {
        // Un clou vu de côté : la tête, puis la pointe ; le point de la figure est la tête.
        canvas.drawLine(
          center,
          center + Offset(0, scale * 1.1),
          Paint()
            ..color = const Color(0xFF9E9E9E)
            ..strokeWidth = math.max(2, scale * 0.18),
        );
        canvas.drawOval(
          Rect.fromCenter(center: center, width: dot * 3, height: dot * 1.4),
          Paint()..color = const Color(0xFF8D6E63),
        );
      } else {
        canvas.drawCircle(center, dot, Paint()..color = color);
      }
      if (selected.contains(p.id)) {
        canvas.drawCircle(
          center,
          dot * 2.6,
          Paint()
            ..color = LudiColors.primary
            ..style = PaintingStyle.stroke
            ..strokeWidth = 3,
        );
      }
      final label = TextPainter(
        text: TextSpan(
          text: p.id,
          style: font.copyWith(
            color: color,
            fontSize: math.max(11, scale * 0.6),
            fontWeight: FontWeight.w700,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      label.paint(canvas, center + Offset(dot * 1.6, -dot * 2.6));
    }
  }

  @override
  bool shouldRepaint(_SheetPainter old) =>
      old.selected.length != selected.length || old.points != points || old.scale != scale;
}
