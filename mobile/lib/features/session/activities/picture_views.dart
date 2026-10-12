import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../app/api_image.dart';
import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Apprendre par l'image (étape 28) : les images des notions, validées par le parent.
/// Aucune image ne porte de légende : seule son adresse est connue de l'application.

const _pairColors = [
  Color(0xFF5B4FE0),
  Color(0xFFFF9F1C),
  Color(0xFF2EB872),
  Color(0xFF1E88E5),
  Color(0xFFD81B60),
  Color(0xFF6D4C41),
];

typedef _Picture = ({String id, String image});

List<_Picture> _picturesOf(Object? list) => [
  for (final p in list as List<dynamic>)
    (id: (p as Json)['id'] as String, image: p['image'] as String),
];

/// Une image à toucher, encadrée de la couleur de sa paire ; numérotée pour la correction.
class _PictureTile extends StatelessWidget {
  const _PictureTile({
    required this.picture,
    required this.number,
    required this.onTap,
    this.color,
    this.selected = false,
  });

  final _Picture picture;
  final int number;
  final VoidCallback? onTap;
  final Color? color;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final border = color ?? (selected ? LudiColors.primary : Colors.black26);
    return Semantics(
      button: true,
      selected: selected || color != null,
      label: 'Image $number',
      excludeSemantics: true,
      child: Material(
        color: Colors.white,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: border, width: selected || color != null ? 4 : 1),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: AspectRatio(
            aspectRatio: 1,
            child: Stack(
              fit: StackFit.expand,
              children: [
                ApiImage(picture.image),
                Positioned(
                  left: 6,
                  top: 6,
                  child: CircleAvatar(
                    radius: 14,
                    backgroundColor: color ?? Colors.black54,
                    child: Text(
                      '$number',
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

Widget _grid(List<Widget> tiles) => LayoutBuilder(
  builder: (context, constraints) {
    final columns = constraints.maxWidth > 520 ? 3 : 2;
    final width = (constraints.maxWidth - 12 * (columns - 1)) / columns;
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [for (final tile in tiles) SizedBox(width: width, child: tile)],
    );
  },
);

/// Image et mot : `{prompt, pictures:[{id,image}], words:[{id,text}]}` → `{pairs:[[image, mot]…]}`.
/// Toucher une image puis un mot (ou l'inverse) les relie ; toucher un élément relié le détache.
class PictureMatchView extends StatefulWidget {
  const PictureMatchView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<PictureMatchView> createState() => _PictureMatchViewState();
}

class _PictureMatchViewState extends State<PictureMatchView> {
  late final List<_Picture> _pictures = _picturesOf(widget.payload['pictures']);
  late final List<Choice> _words = choicesOf(widget.payload['words']);
  final _pairs = <String, String>{}; // image → mot
  String? _picture;
  String? _word;
  bool _sent = false;

  Color? _colorOfPicture(String id) {
    final index = _pairs.keys.toList().indexOf(id);
    return index < 0 ? null : _pairColors[index % _pairColors.length];
  }

  Color? _colorOfWord(String id) {
    final picture = _pairs.entries.where((e) => e.value == id).firstOrNull?.key;
    return picture == null ? null : _colorOfPicture(picture);
  }

  void _tapPicture(String id) => setState(() {
    if (_pairs.remove(id) != null) return;
    _picture = _picture == id ? null : id;
    _link();
  });

  void _tapWord(String id) => setState(() {
    final linked = _pairs.entries.where((e) => e.value == id).firstOrNull;
    if (linked != null) {
      _pairs.remove(linked.key);
      return;
    }
    _word = _word == id ? null : id;
    _link();
  });

  void _link() {
    final (picture, word) = (_picture, _word);
    if (picture == null || word == null) return;
    _pairs[picture] = word;
    _picture = _word = null;
  }

  void _submit() {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit({
      'pairs': [
        for (final MapEntry(:key, :value) in _pairs.entries) [key, value],
      ],
    });
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(
        ActivityInstruction.of(context) ?? 'Relie chaque image au mot qui lui correspond.',
        style: Theme.of(context).textTheme.titleLarge,
      ),
      const SizedBox(height: 16),
      _grid([
        for (final (i, p) in _pictures.indexed)
          _PictureTile(
            picture: p,
            number: i + 1,
            selected: _picture == p.id,
            color: _colorOfPicture(p.id),
            onTap: _sent ? null : () => _tapPicture(p.id),
          ),
      ]),
      const SizedBox(height: 16),
      Wrap(
        alignment: WrapAlignment.center,
        spacing: 10,
        runSpacing: 10,
        children: [
          for (final w in _words)
            _WordChip(
              text: w.text,
              selected: _word == w.id,
              color: _colorOfWord(w.id),
              onTap: _sent ? null : () => _tapWord(w.id),
            ),
        ],
      ),
      const SizedBox(height: 16),
      FilledButton(
        onPressed: _pairs.length == _pictures.length && !_sent ? _submit : null,
        child: Text(
          _pairs.length == _pictures.length
              ? 'Valider'
              : 'Encore ${_pictures.length - _pairs.length} image(s) à relier',
        ),
      ),
    ],
  );
}

class _WordChip extends StatelessWidget {
  const _WordChip({required this.text, required this.onTap, this.selected = false, this.color});

  final String text;
  final VoidCallback? onTap;
  final bool selected;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final border = color ?? (selected ? LudiColors.primary : LudiColors.accent);
    return Semantics(
      button: true,
      selected: selected || color != null,
      label: text,
      excludeSemantics: true,
      child: Material(
        color: color?.withValues(alpha: 0.18) ?? LudiColors.accent.withValues(alpha: 0.12),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: border, width: selected || color != null ? 3 : 2),
        ),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            child: Text(text, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
          ),
        ),
      ),
    );
  }
}

/// Quelle image ? : `{prompt, pictures:[{id,image}], clues:[{id,text}]}` → `{answers:[[phrase, image]…]}`.
/// Une phrase à la fois ; l'image choisie disparaît.
class PictureFindView extends StatefulWidget {
  const PictureFindView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<PictureFindView> createState() => _PictureFindViewState();
}

class _PictureFindViewState extends State<PictureFindView> {
  late final List<_Picture> _pictures = _picturesOf(widget.payload['pictures']);
  late final List<Choice> _clues = choicesOf(widget.payload['clues']);
  final _answers = <List<String>>[];

  void _choose(String picture) {
    if (_answers.length >= _clues.length) return;
    setState(() => _answers.add([_clues[_answers.length].id, picture]));
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
          '🖼️ Quelle image ? · ${math.min(_answers.length + 1, _clues.length)}/${_clues.length}',
          style: Theme.of(context).textTheme.labelLarge?.copyWith(color: LudiColors.primary),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(
            ActivityInstruction.of(context) ?? 'Lis la phrase, puis touche l\'image qui la montre.',
            style: const TextStyle(fontSize: 16, color: Colors.black54),
          ),
        ),
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
            style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
        const SizedBox(height: 20),
        _grid([
          for (final (i, p) in _pictures.indexed)
            if (!used.contains(p.id))
              _PictureTile(picture: p, number: i + 1, onTap: done ? null : () => _choose(p.id)),
        ]),
      ],
    );
  }
}
