//! Safe Prompt Cryptographic Core — ML-KEM-1024 via QoreSeal
//! PyO3 bindings for Python integration with zeroize memory protection.

#![forbid(unsafe_code)]
#![warn(missing_debug_implementations)]

use pyo3::prelude::*;
use pyo3::exceptions::{PyValueError, PyRuntimeError};
use qoreseal::{
    envelope::{seal, open, parse_envelope, SealArgs, envelope_to_text, envelope_from_text, ParsedEnvelope},
    keys::{generate_seal_keys, SealKeyPair, SealRecipient, validate_mlkem_public_key, validate_x25519_public_key},
    errors::{Error as QoresealError, Result as QoresealResult},
    constants::SealMode,
};
use zeroize::{Zeroize, Zeroizing};
use std::sync::Arc;
use base64::Engine as _;

/// Python-facing ML-KEM-1024 envelope (base64url text form)
#[pyclass]
#[derive(Clone)]
pub struct Envelope {
    inner: String,
}

#[pymethods]
impl Envelope {
    #[new]
    fn new(text: String) -> Self {
        Self { inner: text }
    }

    #[getter]
    fn text(&self) -> String {
        self.inner.clone()
    }

    fn __repr__(&self) -> String {
        format!("Envelope({})", self.inner)
    }

    fn __str__(&self) -> String {
        self.inner.clone()
    }
}

/// Python-facing seal key pair (ML-KEM-1024 + X25519)
#[pyclass]
#[derive(Clone)]
pub struct SealKeys {
    // Secret keys wrapped in Zeroizing for memory protection
    mlkem_secret: Zeroizing<Vec<u8>>,
    mlkem_public: Vec<u8>,
    x25519_secret: Zeroizing<Vec<u8>>,
    x25519_public: Vec<u8>,
}

#[pymethods]
impl SealKeys {
    /// Generate a new random key pair
    #[staticmethod]
    fn generate() -> PyResult<Self> {
        let keys = generate_seal_keys();
        Ok(Self {
            mlkem_secret: Zeroizing::new(keys.mlkem_secret_key.to_vec()),
            mlkem_public: keys.mlkem_public_key.to_vec(),
            x25519_secret: Zeroizing::new(keys.x25519_secret_key.to_vec()),
            x25519_public: keys.x25519_public_key.to_vec(),
        })
    }

    /// Get the ML-KEM-1024 public key (base64url encoded for transport)
    #[getter]
    fn mlkem_public(&self) -> String {
        base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE_NO_PAD,&self.mlkem_public)
    }

    /// Get the X25519 public key (base64url encoded)
    #[getter]
    fn x25519_public(&self) -> String {
        base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE_NO_PAD,&self.x25519_public)
    }

    /// Get the recipient object for this key pair (for sealing to self)
    fn as_recipient(&self) -> PyResult<Recipient> {
        let recipient = SealRecipient {
            mlkem_public_key: self.mlkem_public.clone(),
            x25519_public_key: Some(self.x25519_public.clone()),
        };
        Ok(Recipient { inner: recipient })
    }

    /// Get the raw ML-KEM secret key (for decapsulation - use carefully!)
    /// WARNING: Only call this if you need direct access; normally use `open_envelope`
    #[getter]
    fn mlkem_secret_raw(&self) -> Vec<u8> {
        self.mlkem_secret.to_vec()
    }

    /// Get the raw X25519 secret key
    #[getter]
    fn x25519_secret_raw(&self) -> Vec<u8> {
        self.x25519_secret.to_vec()
    }
}

/// Python-facing recipient for sealing
#[pyclass]
#[derive(Clone)]
pub struct Recipient {
    inner: SealRecipient,
}

#[pymethods]
impl Recipient {
    /// Create a recipient from a base64url-encoded ML-KEM public key (and optional X25519 key)
    #[staticmethod]
    fn from_public_keys(mlkem_public_b64url: String, x25519_public_b64url: Option<String>) -> PyResult<Self> {
        let mlkem_public = base64::Engine::decode(&base64::engine::general_purpose::URL_SAFE_NO_PAD, &mlkem_public_b64url)
            .map_err(|e| PyValueError::new_err(format!("Invalid ML-KEM public key: {}", e)))?;
        validate_mlkem_public_key(&mlkem_public)
            .map_err(|e| PyValueError::new_err(format!("Invalid ML-KEM public key: {}", e)))?;

        let x25519_public = if let Some(x) = x25519_public_b64url {
            let decoded = base64::Engine::decode(&base64::engine::general_purpose::URL_SAFE_NO_PAD, &x)
                .map_err(|e| PyValueError::new_err(format!("Invalid X25519 public key: {}", e)))?;
            let result = validate_x25519_public_key(&decoded)
                .map_err(|e| PyValueError::new_err(format!("Invalid X25519 public key: {}", e)))?;
            Some(decoded)
        } else {
            None
        };

        Ok(Self {
            inner: SealRecipient {
                mlkem_public_key: mlkem_public,
                x25519_public_key: x25519_public,
            }
        })
    }

    #[getter]
    fn mlkem_public(&self) -> String {
        base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE_NO_PAD,&self.inner.mlkem_public_key)
    }

    #[getter]
    fn x25519_public(&self) -> Option<String> {
        self.inner.x25519_public_key.as_ref()
            .map(|k| base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE_NO_PAD,k))
    }
}

/// Seal (encrypt) plaintext to one or more recipients using ML-KEM-1024
/// Returns the envelope in base64url text form ("qoreseal:...")
#[pyfunction]
fn seal_envelope(
    chain_id: &str,
    purpose: &str,
    recipients: Vec<Recipient>,
    plaintext: Vec<u8>,
    mode: Option<String>,
    anonymous: Option<bool>,
    aad: Option<Vec<u8>>,
) -> PyResult<String> {
    let mode = match mode.as_deref() {
        Some("mlkem") => qoreseal::SealMode::Mlkem,
        None | Some("hybrid") => qoreseal::SealMode::Hybrid,
        Some(m) => return Err(PyValueError::new_err(format!("Invalid mode: {}", m))),
    };

    let seal_recipients: Vec<SealRecipient> = recipients.into_iter().map(|r| r.inner).collect();
    // SealArgs::new sets defaults: hybrid mode, no AAD, hints on
    let args = SealArgs {
        chain_id,
        purpose,
        recipients: &seal_recipients,
        plaintext: &plaintext,
        aad: aad.as_deref().unwrap_or(&[]),
        mode,
        anonymous: anonymous.unwrap_or(false),
    };

    let envelope_bytes = seal(&args)
        .map_err(|e| PyRuntimeError::new_err(format!("Sealing failed: {}", e)))?;

    Ok(envelope_to_text(&envelope_bytes))
}

/// Open (decrypt) an envelope using the recipient's key pair
/// Returns the plaintext bytes
#[pyfunction]
fn open_envelope(
    chain_id: &str,
    purpose: &str,
    envelope: &str,
    mlkem_secret: Vec<u8>,
    x25519_secret: Vec<u8>,
    mlkem_public: Vec<u8>,
    x25519_public: Vec<u8>,
    aad: Option<Vec<u8>>,
) -> PyResult<Vec<u8>> {
    // Reconstruct the key pair from raw bytes.
    // ML-KEM-1024 keys are 1568/3168 bytes; X25519 keys are 32 bytes.
    // SealKeyPair requires a seed field (not used for decryption), use dummy.
    let keys = SealKeyPair {
        seed: vec![0u8; 32], // dummy seed - not used for decryption
        mlkem_secret_key: mlkem_secret,
        mlkem_public_key: mlkem_public,
        x25519_secret_key: x25519_secret,
        x25519_public_key: x25519_public,
    };

    let envelope_bytes = envelope_from_text(envelope)
        .map_err(|e| PyValueError::new_err(format!("Invalid envelope text: {}", e)))?;

    let plaintext = open(chain_id, purpose, &envelope_bytes, &keys, aad.as_deref().unwrap_or(&[]))
        .map_err(|e| PyRuntimeError::new_err(format!("Opening failed: {}", e)))?;

    Ok(plaintext)
}

/// Open an envelope using a SealKeys object (convenience method)
#[pyfunction]
fn open_envelope_with_keys(
    chain_id: &str,
    purpose: &str,
    envelope: &str,
    keys: &SealKeys,
    aad: Option<Vec<u8>>,
) -> PyResult<Vec<u8>> {
    let plaintext = open_envelope(
        chain_id,
        purpose,
        envelope,
        keys.mlkem_secret.to_vec(),
        keys.x25519_secret.to_vec(),
        keys.mlkem_public.clone(),
        keys.x25519_public.clone(),
        aad,
    )?;
    Ok(plaintext)
}

/// Parse an envelope without decrypting (inspect metadata)
#[pyfunction]
fn parse_envelope_info(envelope: &str) -> PyResult<ParsedEnvelopeInfo> {
    let envelope_bytes = envelope_from_text(envelope)
        .map_err(|e| PyValueError::new_err(format!("Invalid envelope text: {}", e)))?;

    let parsed = parse_envelope(&envelope_bytes)
        .map_err(|e| PyRuntimeError::new_err(format!("Parse failed: {}", e)))?;

    let entries = parsed.entries.iter().map(|e| EnvelopeEntryInfo {
        hint: base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE_NO_PAD,&e.hint),
        mlkem_ciphertext: base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE_NO_PAD,&e.mlkem_ciphertext),
        x25519_ciphertext: e.x25519_ciphertext.as_ref()
            .map(|x| base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE_NO_PAD,x)),
        wrapped_key: base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE_NO_PAD,&e.wrapped_key),
    }).collect();

    Ok(ParsedEnvelopeInfo {
        version: parsed.version,
        mode: match parsed.mode { qoreseal::SealMode::Hybrid => "hybrid", qoreseal::SealMode::Mlkem => "mlkem" }.to_string(),
        anonymous: parsed.anonymous,
        salt: base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE_NO_PAD,&parsed.salt),
        entries,
        nonce: base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE_NO_PAD,&parsed.nonce),
    })
}

/// Python-facing parsed envelope info
#[pyclass]
#[derive(Clone)]
pub struct ParsedEnvelopeInfo {
    version: u8,
    mode: String,
    anonymous: bool,
    salt: String,
    entries: Vec<EnvelopeEntryInfo>,
    nonce: String,
}

#[pymethods]
impl ParsedEnvelopeInfo {
    #[getter] fn version(&self) -> u8 { self.version }
    #[getter] fn mode(&self) -> String { self.mode.clone() }
    #[getter] fn anonymous(&self) -> bool { self.anonymous }
    #[getter] fn salt(&self) -> String { self.salt.clone() }
    #[getter] fn entries(&self) -> Vec<EnvelopeEntryInfo> { self.entries.clone() }
    #[getter] fn nonce(&self) -> String { self.nonce.clone() }
}

/// Python-facing envelope entry info
#[pyclass]
#[derive(Clone)]
pub struct EnvelopeEntryInfo {
    hint: String,
    mlkem_ciphertext: String,
    x25519_ciphertext: Option<String>,
    wrapped_key: String,
}

#[pymethods]
impl EnvelopeEntryInfo {
    #[getter] fn hint(&self) -> String { self.hint.clone() }
    #[getter] fn mlkem_ciphertext(&self) -> String { self.mlkem_ciphertext.clone() }
    #[getter] fn x25519_ciphertext(&self) -> Option<String> { self.x25519_ciphertext.clone() }
    #[getter] fn wrapped_key(&self) -> String { self.wrapped_key.clone() }
}

/// Compute the size of an envelope in bytes (before base64 encoding)
#[pyfunction]
fn envelope_size(mode: &str, num_recipients: usize, plaintext_len: usize) -> PyResult<usize> {
    let mode = match mode {
        "hybrid" => qoreseal::SealMode::Hybrid,
        "mlkem" => qoreseal::SealMode::Mlkem,
        _ => return Err(PyValueError::new_err("Invalid mode")),
    };
    Ok(qoreseal::envelope::envelope_size(mode, num_recipients, plaintext_len))
}

/// Exception classes
mod exceptions {
    use pyo3::create_exception;

    create_exception!(safe_prompt_core, QoresealError, pyo3::exceptions::PyRuntimeError);
    create_exception!(safe_prompt_core, InvalidKeyError, pyo3::exceptions::PyValueError);
    create_exception!(safe_prompt_core, DecryptionError, pyo3::exceptions::PyRuntimeError);
}

/// Module definition
#[pymodule]
fn safe_prompt_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Envelope>()?;
    m.add_class::<SealKeys>()?;
    m.add_class::<Recipient>()?;
    m.add_class::<ParsedEnvelopeInfo>()?;
    m.add_class::<EnvelopeEntryInfo>()?;

    m.add_function(wrap_pyfunction!(seal_envelope, m)?)?;
    m.add_function(wrap_pyfunction!(open_envelope, m)?)?;
    m.add_function(wrap_pyfunction!(open_envelope_with_keys, m)?)?;
    m.add_function(wrap_pyfunction!(parse_envelope_info, m)?)?;
    m.add_function(wrap_pyfunction!(envelope_size, m)?)?;

    m.add("QoresealError", m.py().get_type_bound::<exceptions::QoresealError>())?;
    m.add("InvalidKeyError", m.py().get_type_bound::<exceptions::InvalidKeyError>())?;
    m.add("DecryptionError", m.py().get_type_bound::<exceptions::DecryptionError>())?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use qoreseal::keys::generate_seal_keys;

    #[test]
    fn test_generate_keys() {
        let keys = SealKeys::generate().unwrap();
        // In Rust, accessing the field gives raw bytes:
        //   ML-KEM-1024 public key = 1568 bytes
        //   X25519 public key      = 32 bytes
        assert_eq!(keys.mlkem_public.len(), 1568);
        assert_eq!(keys.x25519_public.len(), 32);
    }

    #[test]
    fn test_seal_open_roundtrip() {
        let alice = SealKeys::generate().unwrap();
        let recipient = alice.as_recipient().unwrap();

        let plaintext = b"Hello, QoreChain PQC!";
        let envelope = seal_envelope("qorechain-diana", "chat", vec![recipient], plaintext.to_vec(), None, None, None).unwrap();

        let opened = open_envelope_with_keys("qorechain-diana", "chat", &envelope, &alice, None).unwrap();
        assert_eq!(opened, plaintext);
    }

    #[test]
    fn test_multi_recipient() {
        let alice = SealKeys::generate().unwrap();
        let bob = SealKeys::generate().unwrap();
        let charlie = SealKeys::generate().unwrap();

        let plaintext = b"Multi-recipient secret";
        let envelope = seal_envelope(
            "qorechain-diana",
            "team-chat",
            vec![alice.as_recipient().unwrap(), bob.as_recipient().unwrap(), charlie.as_recipient().unwrap()],
            plaintext.to_vec(),
            None, None, None
        ).unwrap();

        // All three can open
        for keys in [&alice, &bob, &charlie] {
            let opened = open_envelope_with_keys("qorechain-diana", "team-chat", &envelope, keys, None).unwrap();
            assert_eq!(opened, plaintext);
        }
    }

    #[test]
    fn test_wrong_recipient_cannot_open() {
        let alice = SealKeys::generate().unwrap();
        let bob = SealKeys::generate().unwrap();

        let envelope = seal_envelope("qorechain-diana", "chat", vec![alice.as_recipient().unwrap()], b"secret".to_vec(), None, None, None).unwrap();

        // Bob cannot open
        let result = open_envelope_with_keys("qorechain-diana", "chat", &envelope, &bob, None);
        assert!(result.is_err());
    }

    #[test]
    fn test_parse_envelope() {
        let alice = SealKeys::generate().unwrap();
        let envelope = seal_envelope("qorechain-diana", "chat", vec![alice.as_recipient().unwrap()], b"test".to_vec(), None, None, None).unwrap();

        let info = parse_envelope_info(&envelope).unwrap();
        assert_eq!(info.version, 1);
        assert_eq!(info.mode, "hybrid");
        assert_eq!(info.entries.len(), 1);
    }

    #[test]
    fn test_envelope_size() {
        let size = envelope_size("hybrid", 1, 100).unwrap();
        assert!(size > 100);
    }
}