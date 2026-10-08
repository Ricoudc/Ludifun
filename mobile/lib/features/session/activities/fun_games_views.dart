import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Jeux de l'étape 26 : démêler, trouver la correspondance, roue aléatoire, ouvrir la boîte,
/// cartes aléatoires. Le hasard (case de la roue, ordre des cartes) est décidé par le serveur.

const _colors = [
  LudiColors.primary,
  LudiColors.accent,
  LudiColors.mastered,
  Color(0xFF1E88E5),
  Color(0xFFD81B60),
  Color(0xFF6D4C41),
];

/// Étiquette de mot ou de réponse, à toucher.
class _Chip extends StatelessWidget {
  const _Chip({required this.text, required this.onTap, this.filled = false});

  final String text;
  final VoidCallback? onTap;
  final bool filled;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: text,
    excludeSemantics: true,
    child: Material(
      color: filled ? LudiColors.primary : LudiColors.accent.withValues(alpha: 0.15),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: filled ? LudiColors.primary : LudiColors.accent, width: 2),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Text(
            text,
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: filled ? Colors.white : Colors.black87,
            ),
          ),
        ),
      ),
    ),
  );
}

Widget _hint(BuildContext context, String fallback) => Padding(
  padding: const EdgeInsets.only(top: 8),
  child: Text(
    ActivityInstruction.of(context) ?? fallback,
    style: const TextStyle(fontSize: 16, color: Colors.black54),
  ),
);

/// Démêler : `{prompt, words:[{id,text}]}` → `{order:[id…]}`.
class UnjumbleView extends StatefulWidget {
  const UnjumbleView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<UnjumbleView> createState() => _UnjumbleViewState();
}

class _UnjumbleViewState extends State<UnjumbleView> {
  late final List<Choice> _words = choicesOf(widget.payload['words']);
  final _order = <String>[];
  bool _sent = false;

  String _text(String id) => _words.firstWhere((w) => w.id == id).text;

  void _toggle(String id) {
    if (_sent) return;
    setState(() => _order.contains(id) ? _order.remove(id) : _order.add(id));
  }

  void _submit() {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit({'order': List.of(_order)});
  }

  @override
  Widget build(BuildContext context) {
    final left = _words.where((w) => !_order.contains(w.id)).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String? ?? 'Remets les mots dans l\'ordre.',
          label: '🧶 Démêler',
        ),
        _hint(context, 'Touche les mots dans l\'ordre ; touche un mot placé pour le retirer.'),
        const SizedBox(height: 20),
        Container(
          constraints: const BoxConstraints(minHeight: 72),
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: LudiColors.primary, width: 3)),
          ),
          child: Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final id in _order)
                _Chip(text: _text(id), filled: true, onTap: () => _toggle(id)),
            ],
          ),
        ),
        const SizedBox(height: 24),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 10,
          runSpacing: 10,
          children: [for (final w in left) _Chip(text: w.text, onTap: () => _toggle(w.id))],
        ),
        const SizedBox(height: 24),
        FilledButton(
          onPressed: left.isEmpty && !_sent ? _submit : null,
          child: Text(left.isEmpty ? 'Valider' : 'Encore ${left.length} mot(s)'),
        ),
      ],
    );
  }
}

/// Trouver la correspondance : `{prompt, targets:[{id,text}], clues:[{id,text}]}`
/// → `{answers:[[clue, target]…]}`. Un indice à la fois ; la réponse choisie disparaît.
class FindMatchView extends StatefulWidget {
  const FindMatchView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<FindMatchView> createState() => _FindMatchViewState();
}

class _FindMatchViewState extends State<FindMatchView> {
  late final List<Choice> _targets = choicesOf(widget.payload['targets']);
  late final List<Choice> _clues = choicesOf(widget.payload['clues']);
  final _answers = <List<String>>[];

  void _choose(String target) {
    if (_answers.length >= _clues.length) return;
    setState(() => _answers.add([_clues[_answers.length].id, target]));
    if (_answers.length == _clues.length) {
      widget.onSubmit({
        'answers': [for (final a in _answers) List.of(a)],
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final done = _answers.length >= _clues.length;
    final used = {for (final a in _answers) a[1]};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '🔎 Trouver la correspondance · ${math.min(_answers.length + 1, _clues.length)}/${_clues.length}',
          style: Theme.of(context).textTheme.labelLarge?.copyWith(color: LudiColors.primary),
        ),
        _hint(context, 'Lis l\'indice, puis touche la réponse qui va avec.'),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: LudiColors.primary.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(18),
          ),
          child: Text(
            done ? 'Bravo, c\'est fini !' : _clues[_answers.length].text,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
        const SizedBox(height: 24),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 10,
          runSpacing: 10,
          children: [
            for (final t in _targets)
              if (!used.contains(t.id))
                _Chip(text: t.text, onTap: done ? null : () => _choose(t.id)),
          ],
        ),
      ],
    );
  }
}

/// Une question à choix d'un jeu de hasard : `{id, prompt, choices, passage?}`.
class _ChoiceQuestion extends StatelessWidget {
  const _ChoiceQuestion({required this.question, required this.onChoose});

  final Json question;
  final ValueChanged<String> onChoose;

  @override
  Widget build(BuildContext context) {
    final choices = choicesOf(question['choices']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          question['prompt'] as String,
          passage: question['passage'] as String?,
          source: question['source'] as String?,
        ),
        const SizedBox(height: 16),
        for (final (i, c) in choices.indexed) ...[
          AnswerButton(
            label: c.text,
            leading: String.fromCharCode(65 + i),
            color: _colors[i % _colors.length],
            onPressed: () => onChoose(c.id),
          ),
          const SizedBox(height: 10),
        ],
      ],
    );
  }
}

/// Roue aléatoire : `{prompt, segments:[{id,text}], spins:[{id, segment, prompt, choices}]}`
/// → `{answers:[{id, choice_id}]}`. La roue s'arrête sur la case choisie par le serveur.
class WheelView extends StatefulWidget {
  const WheelView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<WheelView> createState() => _WheelViewState();
}

class _WheelViewState extends State<WheelView> with SingleTickerProviderStateMixin {
  late final List<Choice> _segments = choicesOf(widget.payload['segments']);
  late final List<Json> _spins = [
    for (final s in widget.payload['spins'] as List<dynamic>) s as Json,
  ];
  late final _controller = AnimationController(vsync: this, duration: const Duration(seconds: 2));
  final _answers = <Map<String, String>>[];
  double _from = 0, _to = 0;
  bool _spinning = false, _landed = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _spin() async {
    if (_spinning || _landed || _answers.length >= _spins.length) return;
    final segment = _segments.indexWhere((s) => s.id == _spins[_answers.length]['segment']);
    final sweep = 2 * math.pi / _segments.length;
    setState(() {
      _spinning = true;
      _from = _to;
      // Plusieurs tours, puis le milieu de la case sous la flèche (en haut).
      _to = 2 * math.pi * 5 * (_answers.length + 1) - (segment + 0.5) * sweep;
    });
    await _controller.forward(from: 0);
    if (mounted) {
      setState(() {
        _spinning = false;
        _landed = true;
      });
    }
  }

  void _answer(String choice) {
    setState(() {
      _answers.add({'id': _spins[_answers.length]['id'] as String, 'choice_id': choice});
      _landed = false;
    });
    if (_answers.length == _spins.length) widget.onSubmit({'answers': List.of(_answers)});
  }

  @override
  Widget build(BuildContext context) {
    final done = _answers.length >= _spins.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '🎡 Roue aléatoire · question ${math.min(_answers.length + 1, _spins.length)}/${_spins.length}',
          style: Theme.of(context).textTheme.labelLarge?.copyWith(color: LudiColors.primary),
        ),
        _hint(context, 'Fais tourner la roue : elle choisit ta question.'),
        const SizedBox(height: 12),
        if (_landed && !done)
          _ChoiceQuestion(question: _spins[_answers.length], onChoose: _answer)
        else ...[
          Center(
            child: SizedBox(
              width: 260,
              height: 280,
              child: Stack(
                alignment: Alignment.topCenter,
                children: [
                  Positioned(
                    top: 20,
                    child: AnimatedBuilder(
                      animation: _controller,
                      builder: (_, _) => Transform.rotate(
                        angle:
                            _from +
                            (_to - _from) * Curves.easeOutCubic.transform(_controller.value),
                        child: CustomPaint(
                          size: const Size(250, 250),
                          painter: _WheelPainter([for (final s in _segments) s.text]),
                        ),
                      ),
                    ),
                  ),
                  const Icon(Icons.arrow_drop_down, size: 48, color: Colors.black87),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _spinning || done ? null : _spin,
            icon: const Icon(Icons.refresh),
            label: Text(done ? 'Terminé' : 'Faire tourner la roue'),
          ),
        ],
      ],
    );
  }
}

class _WheelPainter extends CustomPainter {
  _WheelPainter(this.labels);

  final List<String> labels;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.width / 2;
    final sweep = 2 * math.pi / labels.length;
    final rect = Rect.fromCircle(center: center, radius: radius);
    for (var i = 0; i < labels.length; i++) {
      final start = -math.pi / 2 + i * sweep;
      canvas.drawArc(rect, start, sweep, true, Paint()..color = _colors[i % _colors.length]);
      final middle = start + sweep / 2;
      final text = TextPainter(
        text: TextSpan(text: labels[i], style: const TextStyle(fontSize: 30)),
        textDirection: TextDirection.ltr,
      )..layout();
      final at = center + Offset(math.cos(middle), math.sin(middle)) * radius * 0.62;
      text.paint(canvas, at - Offset(text.width / 2, text.height / 2));
    }
    canvas.drawCircle(center, 14, Paint()..color = Colors.white);
  }

  @override
  bool shouldRepaint(_WheelPainter old) => old.labels != labels;
}

/// Ouvrir la boîte : `{prompt, boxes:[{id, number, prompt, choices}]}` → `{answers:[{id, choice_id}]}`.
class BoxView extends StatefulWidget {
  const BoxView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<BoxView> createState() => _BoxViewState();
}

class _BoxViewState extends State<BoxView> {
  late final List<Json> _boxes = [
    for (final b in widget.payload['boxes'] as List<dynamic>) b as Json,
  ];
  final _answers = <String, String>{};
  Json? _open;

  void _answer(String choice) {
    setState(() {
      _answers[_open!['id'] as String] = choice;
      _open = null;
    });
    if (_answers.length == _boxes.length) {
      widget.onSubmit({
        'answers': [
          for (final e in _answers.entries) {'id': e.key, 'choice_id': e.value},
        ],
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final open = _open;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '🎁 Ouvrir la boîte · ${_answers.length}/${_boxes.length}',
          style: Theme.of(context).textTheme.labelLarge?.copyWith(color: LudiColors.primary),
        ),
        _hint(context, 'Touche une boîte pour l\'ouvrir, puis réponds à la question.'),
        const SizedBox(height: 16),
        if (open != null)
          _ChoiceQuestion(question: open, onChoose: _answer)
        else
          Wrap(
            alignment: WrapAlignment.center,
            spacing: 14,
            runSpacing: 14,
            children: [
              for (final (i, box) in _boxes.indexed)
                _BoxTile(
                  number: box['number'] as int? ?? i + 1,
                  color: _colors[i % _colors.length],
                  opened: _answers.containsKey(box['id']),
                  onTap: () => setState(() => _open = box),
                ),
            ],
          ),
      ],
    );
  }
}

class _BoxTile extends StatelessWidget {
  const _BoxTile({
    required this.number,
    required this.color,
    required this.opened,
    required this.onTap,
  });

  final int number;
  final Color color;
  final bool opened;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: !opened,
    label: opened ? 'Boîte $number, déjà ouverte' : 'Boîte $number',
    excludeSemantics: true,
    child: Material(
      color: opened ? Colors.black12 : color,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: opened ? null : onTap,
        borderRadius: BorderRadius.circular(16),
        child: SizedBox(
          width: 96,
          height: 96,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(opened ? '✔️' : '🎁', style: const TextStyle(fontSize: 34)),
              Text(
                '$number',
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  color: opened ? Colors.black45 : Colors.white,
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

/// Cartes aléatoires : `{prompt, cards:[{id, front, back}]}` → `{cards:[{id, knew}]}`.
class RandomCardsView extends StatefulWidget {
  const RandomCardsView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<RandomCardsView> createState() => _RandomCardsViewState();
}

class _RandomCardsViewState extends State<RandomCardsView> {
  late final List<Json> _cards = [
    for (final c in widget.payload['cards'] as List<dynamic>) c as Json,
  ];
  final _results = <Map<String, Object>>[];
  bool _drawn = false, _flipped = false;

  void _assess(bool knew) {
    setState(() {
      _results.add({'id': _cards[_results.length]['id'] as String, 'knew': knew});
      _drawn = _flipped = false;
    });
    if (_results.length == _cards.length) widget.onSubmit({'cards': List.of(_results)});
  }

  @override
  Widget build(BuildContext context) {
    final done = _results.length >= _cards.length;
    final card = done ? null : _cards[_results.length];
    final left = _cards.length - _results.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '🃏 Cartes aléatoires · $left carte(s) dans le paquet',
          style: Theme.of(context).textTheme.labelLarge?.copyWith(color: LudiColors.primary),
        ),
        _hint(context, 'Tire une carte, essaie de répondre, puis retourne-la.'),
        const SizedBox(height: 16),
        if (card == null)
          const Center(child: Text('Paquet terminé !', style: TextStyle(fontSize: 22)))
        else if (!_drawn) ...[
          Center(
            child: SizedBox(
              width: 180,
              height: 220,
              child: Stack(
                children: [
                  for (var i = math.min(left, 3) - 1; i >= 0; i--)
                    Positioned(
                      left: i * 8.0,
                      top: i * 8.0,
                      child: Container(
                        width: 160,
                        height: 200,
                        decoration: BoxDecoration(
                          color: LudiColors.primary,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: Colors.white, width: 3),
                        ),
                        child: const Center(child: Text('❓', style: TextStyle(fontSize: 48))),
                      ),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: () => setState(() => _drawn = true),
            icon: const Icon(Icons.style),
            label: const Text('Tirer une carte'),
          ),
        ] else ...[
          GestureDetector(
            onTap: () => setState(() => _flipped = true),
            child: Card(
              color: _flipped ? LudiColors.accent.withValues(alpha: 0.15) : Colors.white,
              child: Container(
                constraints: const BoxConstraints(minHeight: 180),
                alignment: Alignment.center,
                padding: const EdgeInsets.all(24),
                child: Text(
                  (_flipped ? card['back'] : card['front']) as String,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall
                      ?.copyWith(fontWeight: FontWeight.w700),
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          if (!_flipped)
            FilledButton.icon(
              onPressed: () => setState(() => _flipped = true),
              icon: const Icon(Icons.flip),
              label: const Text('Retourner la carte'),
            )
          else
            Row(
              children: [
                Expanded(
                  child: AnswerButton(
                    label: 'Je ne savais pas',
                    color: LudiColors.toReview,
                    onPressed: () => _assess(false),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: AnswerButton(
                    label: 'Je savais',
                    color: LudiColors.mastered,
                    onPressed: () => _assess(true),
                  ),
                ),
              ],
            ),
        ],
      ],
    );
  }
}
