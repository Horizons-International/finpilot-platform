# OCR Framework

## Overview

The OCR framework provides a provider-independent connection layer
for extracting text from customer documents.

## Architecture

Customer Document
    ↓
OCR Service
    ↓
OCR Provider Interface
    ↓
OCR Provider
    ↓
OCR Result

## Processing Status

- Submitted
- Processing
- Completed
- Failed

## Provider Interface

Providers implement:

`OCRProvider.process(OCRRequest) -> OCRResponse`

## Configuration

```env
OCR_PROVIDER=mock