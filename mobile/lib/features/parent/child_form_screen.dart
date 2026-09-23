import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/subject.dart';
import 'parent_providers.dart';

/// Écran P2 : ajout d'un enfant (avec le consentement parental) ou modification du profil.
class ChildFormScreen extends ConsumerStatefulWidget {
  const ChildFormScreen({this.childId, super.key});

  /// `null` : nouvel enfant.
  final String? childId;

  @override
  ConsumerState<ChildFormScreen> createState() => _ChildFormScreenState();
}

class _ChildFormScreenState extends ConsumerState<ChildFormScreen> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  String? _grade;
  String? _avatar = avatars.first;
  bool _consent = false;
  bool _loaded = false;
  bool _busy = false;
  String? _error;

  bool get _editing => widget.childId != null;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    if (_grade == null) return setState(() => _error = 'Choisissez la classe.');
    if (!_editing && !_consent) {
      return setState(
        () => _error = 'Le consentement parental est nécessaire pour créer le profil.',
      );
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final api = ref.read(apiProvider);
    try {
      final name = _name.text.trim();
      if (_editing) {
        await api.updateChild(widget.childId!, displayName: name, grade: _grade, avatar: _avatar);
        ref.invalidate(childrenProvider);
        if (mounted) context.go(Routes.childSettings(widget.childId!));
      } else {
        final child = await api.createChild(displayName: name, grade: _grade!, avatar: _avatar);
        ref.invalidate(childrenProvider);
        if (mounted) context.go(Routes.childLink(child.id)); // étape suivante : lier sa tablette
      }
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = error.message;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_editing && !_loaded) {
      final child = ref.watch(childProvider(widget.childId!)).value;
      if (child != null) {
        _loaded = true;
        _name.text = child.displayName;
        _grade = child.grade;
        _avatar = child.avatar;
      }
    }
    final theme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(
          onPressed: () =>
              context.go(_editing ? Routes.childSettings(widget.childId!) : Routes.parentHome),
        ),
        title: Text(_editing ? 'Modifier le profil' : 'Ajouter un enfant'),
      ),
      body: Form(
        key: _form,
        child: CenteredBody(
          top: true,
          children: [
            TextFormField(
              controller: _name,
              maxLength: 40,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                labelText: 'Prénom ou pseudo',
                helperText: 'Un pseudo suffit : pas besoin du nom de famille.',
              ),
              validator: (v) =>
                  (v ?? '').trim().isEmpty ? 'Saisissez un prénom ou un pseudo.' : null,
            ),
            const SizedBox(height: 16),
            Text('Classe', style: theme.titleMedium),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final g in grades)
                  ChoiceChip(
                    label: Text(g, style: const TextStyle(fontSize: 16)),
                    selected: _grade == g,
                    onSelected: (_) => setState(() => _grade = g),
                  ),
              ],
            ),
            const SizedBox(height: 20),
            Text('Avatar', style: theme.titleMedium),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final a in avatars)
                  ChoiceChip(
                    label: Text(a, style: const TextStyle(fontSize: 24)),
                    selected: _avatar == a,
                    onSelected: (_) => setState(() => _avatar = a),
                  ),
              ],
            ),
            if (!_editing) ...[
              const SizedBox(height: 16),
              CheckboxListTile(
                value: _consent,
                onChanged: (v) => setState(() => _consent = v ?? false),
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text(
                  'Je suis le parent ou le responsable légal de cet enfant et j\'accepte que ses '
                  'leçons photographiées soient analysées pour préparer ses révisions.',
                ),
              ),
            ],
            if (_error != null) ...[const SizedBox(height: 16), ErrorMessage(_error!)],
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _busy ? null : _submit,
              child: Text(_editing ? 'Enregistrer' : 'Créer le profil'),
            ),
          ],
        ),
      ),
    );
  }
}
