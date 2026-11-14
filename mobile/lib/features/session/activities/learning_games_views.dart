import 'dart:async';

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Jeux d'apprentissage de novembre 2026 (§5.98) : chasse à l'erreur, phrase qui s'efface, le bon
/// ordre, le correcteur, qui suis-je, l'escalier, le train des mots, compte et touche.

/// Étiquette à toucher, grande et lisible.
class _Chip extends StatelessWidget {
  const _Chip(
    this.text, {
    required this.onTap,
    this.color = LudiColors.primary,
    this.selected = false,
  });

  final String text;
  final VoidCallback? onTap;
  final Color color;
  final bool selected;

  @override
  Widget build(BuildContext context) => Material(
    color: selected ? color : color.withValues(alpha: 0.1),
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(14),
      side: BorderSide(color: color, width: 2),
    ),
    clipBehavior: Clip.antiAlias,
    child: InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        child: Text(
          text,
          style: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.w600,
            color: selected ? Colors.white : Colors.black87,
          ),
        ),
      ),
    ),
  );
}

/// Chasse à l'erreur : `{prompt, words:[{id,text}], choices}` → `{word_id, choice_id}`.
class SpotErrorView extends StatefulWidget {
  const SpotErrorView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<SpotErrorView> createState() => _SpotErrorViewState();
}

class _SpotErrorViewState extends State<SpotErrorView> {
  String? _word;
  bool _sent = false;

  void _fix(String choice) {
    if (_sent || _word == null) return;
    setState(() => _sent = true);
    widget.onSubmit({'word_id': _word, 'choice_id': choice});
  }

  @override
  Widget build(BuildContext context) {
    final words = choicesOf(widget.payload['words']);
    final choices = choicesOf(widget.payload['choices']);
    final picked = words.where((w) => w.id == _word).firstOrNull;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String,
          label: ActivityInstruction.of(context) ?? 'Chasse à l\'erreur',
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final w in words)
              _Chip(
                w.text,
                selected: w.id == _word,
                color: LudiColors.accent,
                onTap: _sent ? null : () => setState(() => _word = w.id),
              ),
          ],
        ),
        const SizedBox(height: 24),
        if (picked != null) ...[
          Text(
            'Par quoi remplacer « ${picked.text} » ?',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 12),
          for (final c in choices) ...[
            AnswerButton(label: c.text, onPressed: _sent ? null : () => _fix(c.id)),
            const SizedBox(height: 10),
          ],
        ] else
          const Text('Touche le mot qui est faux.', style: TextStyle(fontSize: 17)),
      ],
    );
  }
}

/// Phrase qui s'efface : `{prompt, words, hidden:[index], memorize_s}` → `{answers:[[index, texte]]}`.
class FadingView extends StatefulWidget {
  const FadingView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<FadingView> createState() => _FadingViewState();
}

class _FadingViewState extends State<FadingView> {
  late final List<String> _words = (widget.payload['words'] as List<dynamic>).cast<String>();
  late final List<int> _hidden = (widget.payload['hidden'] as List<dynamic>).cast<int>();
  late final Map<int, TextEditingController> _fields = {
    for (final i in _hidden) i: TextEditingController(),
  };
  bool _faded = false;
  bool _sent = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    final seconds = widget.payload['memorize_s'] as int? ?? 6;
    _timer = Timer(Duration(seconds: seconds), _fade);
  }

  void _fade() {
    if (mounted && !_faded) setState(() => _faded = true);
  }

  @override
  void dispose() {
    _timer?.cancel();
    for (final c in _fields.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _send() {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit({
      'answers': [
        for (final e in _fields.entries) [e.key, e.value.text.trim()],
      ],
    });
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Prompt(
        widget.payload['prompt'] as String,
        label: ActivityInstruction.of(context) ?? 'Phrase qui s\'efface',
      ),
      const SizedBox(height: 16),
      if (!_faded) ...[
        Text(
          _words.join(' '),
          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700, height: 1.5),
        ),
        const SizedBox(height: 16),
        OutlinedButton(onPressed: _fade, child: const Text('J\'ai retenu, c\'est parti !')),
      ] else ...[
        Wrap(
          spacing: 6,
          runSpacing: 10,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            for (var i = 0; i < _words.length; i++)
              if (_fields[i] case final field?)
                SizedBox(
                  width: 130,
                  child: TextField(
                    controller: field,
                    enabled: !_sent,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 20),
                    decoration: const InputDecoration(isDense: true, hintText: '…'),
                  ),
                )
              else
                Text(_words[i], style: const TextStyle(fontSize: 22)),
          ],
        ),
        const SizedBox(height: 24),
        FilledButton(onPressed: _sent ? null : _send, child: const Text('Valider')),
      ],
    ],
  );
}

/// Le bon ordre : `{prompt, items}` → `{order, intruder}`. L'enfant touche les étapes dans l'ordre ;
/// celle qui est fausse se met de côté.
class StepOrderView extends StatefulWidget {
  const StepOrderView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<StepOrderView> createState() => _StepOrderViewState();
}

class _StepOrderViewState extends State<StepOrderView> {
  final _order = <String>[];
  String? _intruder;
  bool _aside = false;
  bool _sent = false;

  void _tap(String id) {
    if (_sent) return;
    setState(() {
      if (_aside) {
        _intruder = _intruder == id ? null : id;
        _order.remove(id);
        _aside = false;
      } else if (_order.contains(id)) {
        _order.remove(id);
      } else {
        _order.add(id);
        if (_intruder == id) _intruder = null;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final items = choicesOf(widget.payload['items']);
    final ready = _intruder != null && _order.length == items.length - 1;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String,
          label: ActivityInstruction.of(context) ?? 'Le bon ordre',
        ),
        const SizedBox(height: 12),
        for (final item in items) ...[
          AnswerButton(
            label: item.text,
            leading: _order.contains(item.id)
                ? '${_order.indexOf(item.id) + 1}'
                : (_intruder == item.id ? '✗' : null),
            color: _intruder == item.id ? LudiColors.notMastered : LudiColors.primary,
            selected: _order.contains(item.id) || _intruder == item.id,
            onPressed: _sent ? null : () => _tap(item.id),
          ),
          const SizedBox(height: 8),
        ],
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: _sent ? null : () => setState(() => _aside = !_aside),
          icon: const Icon(Icons.block),
          label: Text(_aside ? 'Touche l\'étape fausse…' : 'Mettre une étape de côté'),
        ),
        const SizedBox(height: 8),
        FilledButton(
          onPressed: ready && !_sent
              ? () {
                  setState(() => _sent = true);
                  widget.onSubmit({'order': _order, 'intruder': _intruder});
                }
              : null,
          child: const Text('Valider'),
        ),
      ],
    );
  }
}

/// Le correcteur : `{question, ludi_answer, reasons}` → `{right, reason_id}`.
class CheckLudiView extends StatefulWidget {
  const CheckLudiView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<CheckLudiView> createState() => _CheckLudiViewState();
}

class _CheckLudiViewState extends State<CheckLudiView> {
  bool _wrong = false;
  bool _sent = false;

  void _send(bool right, [String? reason]) {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit({'right': right, 'reason_id': reason});
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Prompt(
        widget.payload['question'] as String,
        label: ActivityInstruction.of(context) ?? 'Le correcteur',
      ),
      const SizedBox(height: 16),
      Card(
        color: LudiColors.accent.withValues(alpha: 0.15),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text(
            '🦉 Ludi a répondu : « ${widget.payload['ludi_answer']} »',
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
          ),
        ),
      ),
      const SizedBox(height: 16),
      if (!_wrong)
        Row(
          children: [
            Expanded(
              child: AnswerButton(
                label: '✅ Il a raison',
                onPressed: _sent ? null : () => _send(true),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: AnswerButton(
                label: '❌ Il se trompe',
                color: LudiColors.accent,
                onPressed: _sent ? null : () => setState(() => _wrong = true),
              ),
            ),
          ],
        )
      else ...[
        const Text(
          'Pourquoi s\'est-il trompé ?',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 10),
        for (final r in choicesOf(widget.payload['reasons'])) ...[
          AnswerButton(label: r.text, onPressed: _sent ? null : () => _send(false, r.id)),
          const SizedBox(height: 8),
        ],
      ],
    ],
  );
}

/// Qui suis-je ? : `{prompt, clues, choices}` → `{choice_id, clues_used}`.
class WhoAmIView extends StatefulWidget {
  const WhoAmIView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<WhoAmIView> createState() => _WhoAmIViewState();
}

class _WhoAmIViewState extends State<WhoAmIView> {
  int _shown = 1;
  bool _sent = false;

  @override
  Widget build(BuildContext context) {
    final clues = (widget.payload['clues'] as List<dynamic>).cast<String>();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String,
          label: ActivityInstruction.of(context) ?? 'Qui suis-je ?',
        ),
        const SizedBox(height: 12),
        for (var i = 0; i < _shown && i < clues.length; i++)
          Card(
            child: ListTile(
              leading: Text('${i + 1}', style: const TextStyle(fontSize: 22)),
              title: Text(clues[i], style: const TextStyle(fontSize: 18)),
            ),
          ),
        if (_shown < clues.length)
          TextButton.icon(
            onPressed: _sent ? null : () => setState(() => _shown++),
            icon: const Icon(Icons.lightbulb_outline),
            label: const Text('Un autre indice'),
          ),
        const SizedBox(height: 12),
        for (final c in choicesOf(widget.payload['choices'])) ...[
          AnswerButton(
            label: c.text,
            onPressed: _sent
                ? null
                : () {
                    setState(() => _sent = true);
                    widget.onSubmit({'choice_id': c.id, 'clues_used': _shown.clamp(1, 3)});
                  },
          ),
          const SizedBox(height: 8),
        ],
      ],
    );
  }
}

/// L'escalier : `{prompt, steps:[{id, prompt, choices}]}` → `{answers:[[marche, choix]]}`.
class StairsView extends StatefulWidget {
  const StairsView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<StairsView> createState() => _StairsViewState();
}

class _StairsViewState extends State<StairsView> {
  final _answers = <List<String>>[];
  bool _sent = false;

  void _answer(String step, String choice, int total) {
    if (_sent) return;
    setState(() => _answers.add([step, choice]));
    if (_answers.length == total) {
      setState(() => _sent = true);
      widget.onSubmit({'answers': _answers});
    }
  }

  @override
  Widget build(BuildContext context) {
    final steps = [for (final s in widget.payload['steps'] as List<dynamic>) s as Json];
    final index = _answers.length.clamp(0, steps.length - 1);
    final step = steps[index];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          ActivityInstruction.of(context) ?? (widget.payload['prompt'] as String),
          style: Theme.of(context).textTheme.labelLarge?.copyWith(color: LudiColors.primary),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            for (var i = 0; i < steps.length; i++)
              Expanded(
                child: Container(
                  height: 10.0 + i * 6,
                  margin: const EdgeInsets.symmetric(horizontal: 2),
                  alignment: Alignment.bottomCenter,
                  decoration: BoxDecoration(
                    color: i < _answers.length ? LudiColors.primary : Colors.black12,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 16),
        Prompt(step['prompt'] as String, label: 'Marche ${index + 1} sur ${steps.length}'),
        const SizedBox(height: 12),
        for (final c in choicesOf(step['choices'])) ...[
          AnswerButton(
            key: ValueKey('${step['id']}-${c.id}'),
            label: c.text,
            onPressed: _sent ? null : () => _answer(step['id'] as String, c.id, steps.length),
          ),
          const SizedBox(height: 8),
        ],
      ],
    );
  }
}

/// Le train des mots : `{prompt, say, wagons, length}` → `{order}`.
class WordTrainView extends StatefulWidget {
  const WordTrainView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<WordTrainView> createState() => _WordTrainViewState();
}

class _WordTrainViewState extends State<WordTrainView> {
  final _train = <String>[];
  bool _sent = false;

  @override
  Widget build(BuildContext context) {
    final wagons = choicesOf(widget.payload['wagons']);
    final length = widget.payload['length'] as int;
    final texts = {for (final w in wagons) w.id: w.text};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String,
          label: ActivityInstruction.of(context) ?? 'Le train des mots',
          listen: false,
        ),
        Center(child: ListenButton([widget.payload['say'] as String])),
        const SizedBox(height: 12),
        Wrap(
          spacing: 4,
          children: [
            const Text('🚂', style: TextStyle(fontSize: 34)),
            for (final id in _train)
              _Chip(
                texts[id]!,
                selected: true,
                onTap: _sent ? null : () => setState(() => _train.remove(id)),
              ),
          ],
        ),
        const SizedBox(height: 20),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final w in wagons)
              if (!_train.contains(w.id))
                _Chip(
                  w.text,
                  color: LudiColors.accent,
                  onTap: _sent || _train.length >= length
                      ? null
                      : () => setState(() => _train.add(w.id)),
                ),
          ],
        ),
        const SizedBox(height: 20),
        FilledButton(
          onPressed: _train.length == length && !_sent
              ? () {
                  setState(() => _sent = true);
                  widget.onSubmit({'order': _train});
                }
              : null,
          child: const Text('Le train part !'),
        ),
      ],
    );
  }
}

/// Compte et touche : `{prompt, say, target, emoji, objects}` → `{selected}`.
class CountTouchView extends StatefulWidget {
  const CountTouchView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<CountTouchView> createState() => _CountTouchViewState();
}

class _CountTouchViewState extends State<CountTouchView> {
  final _selected = <String>{};
  bool _sent = false;

  @override
  Widget build(BuildContext context) {
    final objects = (widget.payload['objects'] as List<dynamic>).cast<String>();
    final emoji = widget.payload['emoji'] as String;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String,
          label: ActivityInstruction.of(context) ?? 'Compte et touche',
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final id in objects)
              InkWell(
                key: ValueKey(id),
                onTap: _sent
                    ? null
                    : () => setState(
                        () => _selected.contains(id) ? _selected.remove(id) : _selected.add(id),
                      ),
                child: Container(
                  width: 54,
                  height: 54,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: _selected.contains(id)
                        ? LudiColors.primary.withValues(alpha: 0.25)
                        : Colors.transparent,
                    border: Border.all(
                      color: _selected.contains(id) ? LudiColors.primary : Colors.black12,
                      width: 2,
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(emoji, style: const TextStyle(fontSize: 30)),
                ),
              ),
          ],
        ),
        const SizedBox(height: 16),
        Text(
          'Touchés : ${_selected.length}',
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 18),
        ),
        const SizedBox(height: 12),
        FilledButton(
          onPressed: _selected.isEmpty || _sent
              ? null
              : () {
                  setState(() => _sent = true);
                  widget.onSubmit({'selected': _selected.toList()});
                },
          child: const Text('J\'ai fini'),
        ),
      ],
    );
  }
}
