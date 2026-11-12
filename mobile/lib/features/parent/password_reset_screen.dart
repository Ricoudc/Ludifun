import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';

/// Écran P1 : « Mot de passe oublié ? » (demande du lien), puis nouveau mot de passe
/// (ouvert par le lien de l'e-mail, avec son jeton).
class PasswordResetScreen extends ConsumerStatefulWidget {
  const PasswordResetScreen({this.token, super.key});

  final String? token;

  @override
  ConsumerState<PasswordResetScreen> createState() => _PasswordResetScreenState();
}

class _PasswordResetScreenState extends ConsumerState<PasswordResetScreen> {
  static const minPassword = 12;
  final _form = GlobalKey<FormState>();
  final _field = TextEditingController();
  bool _busy = false;
  String? _error;
  String? _done;

  bool get _confirming => widget.token != null;

  @override
  void dispose() {
    _field.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final api = ref.read(apiProvider);
    try {
      if (_confirming) {
        await api.confirmPasswordReset(token: widget.token!, newPassword: _field.text);
        await ref.read(sessionProvider.notifier).forget(); // les autres sessions sont fermées
        _done = 'Votre mot de passe est changé. Vous pouvez vous connecter.';
      } else {
        await api.requestPasswordReset(_field.text.trim());
        _done =
            'Si un compte existe pour cette adresse, un lien vient d\'être envoyé. '
            'Ouvrez-le sur ce téléphone.';
      }
    } on ApiException catch (error) {
      _error = error.message;
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      leading: BackButton(onPressed: () => context.go(Routes.parentSignIn)),
      title: Text(_confirming ? 'Nouveau mot de passe' : 'Mot de passe oublié'),
    ),
    body: Form(
      key: _form,
      child: CenteredBody(
        children: [
          if (_done != null) ...[
            Text(_done!, style: const TextStyle(fontSize: 18)),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: () => context.go(Routes.parentSignIn),
              child: const Text('Me connecter'),
            ),
          ] else ...[
            if (_confirming)
              TextFormField(
                controller: _field,
                obscureText: true,
                autofillHints: const [AutofillHints.newPassword],
                decoration: const InputDecoration(
                  labelText: 'Nouveau mot de passe',
                  helperText: 'Au moins $minPassword caractères.',
                ),
                validator: (v) =>
                    (v ?? '').length < minPassword ? 'Au moins $minPassword caractères.' : null,
              )
            else ...[
              const Text(
                'Indiquez l\'adresse de votre compte : nous vous envoyons un lien pour choisir '
                'un nouveau mot de passe.',
                style: TextStyle(fontSize: 17),
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _field,
                keyboardType: TextInputType.emailAddress,
                autofillHints: const [AutofillHints.email],
                decoration: const InputDecoration(labelText: 'Adresse e-mail'),
                validator: (v) =>
                    (v ?? '').contains('@') ? null : 'Saisissez une adresse e-mail valide.',
              ),
            ],
            if (_error != null) ...[const SizedBox(height: 16), ErrorMessage(_error!)],
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _busy ? null : _submit,
              child: Text(_confirming ? 'Changer mon mot de passe' : 'Recevoir le lien'),
            ),
          ],
        ],
      ),
    ),
  );
}
