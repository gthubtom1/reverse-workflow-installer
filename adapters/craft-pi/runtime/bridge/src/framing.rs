use crate::{Failure, Result};
/// LF only. UTF-8 is decoded only after a complete record is available.
pub struct Framer {
    pending: Vec<u8>,
    total: usize,
    record_limit: usize,
    total_limit: usize,
}
impl Framer {
    pub fn new(record_limit: usize, total_limit: usize) -> Self {
        Self {
            pending: Vec::new(),
            total: 0,
            record_limit,
            total_limit,
        }
    }
    pub fn feed(&mut self, bytes: &[u8]) -> Result<Vec<serde_json::Value>> {
        self.total = self
            .total
            .checked_add(bytes.len())
            .ok_or_else(|| Failure::new("output_limit", "overflow"))?;
        if self.total > self.total_limit {
            return Err(Failure::new("output_limit", "stdout total exceeded"));
        }
        let mut records = Vec::new();
        for &byte in bytes {
            if byte == b'\n' {
                if self.pending.last() == Some(&b'\r') {
                    self.pending.pop();
                }
                let text = std::str::from_utf8(&self.pending)
                    .map_err(|e| Failure::new("invalid_utf8", e))?;
                let v: serde_json::Value =
                    serde_json::from_str(text).map_err(|e| Failure::new("bad_json", e))?;
                if !v.is_object() || !v["type"].is_string() {
                    return Err(Failure::new("bad_protocol", "object with type required"));
                }
                records.push(v);
                self.pending.clear();
            } else {
                self.pending.push(byte);
                if self.pending.len() > self.record_limit {
                    return Err(Failure::new("record_limit", "stdout record exceeded"));
                }
            }
        }
        Ok(records)
    }
    pub fn finish(&self) -> Result<()> {
        if self.pending.is_empty() {
            Ok(())
        } else {
            Err(Failure::new("truncated_frame", "stdout ended without LF"))
        }
    }
}
