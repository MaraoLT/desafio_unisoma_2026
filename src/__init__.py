"""Pacote principal do backend e aplicação — Desafio UniSoma 2026 (Equipe 10)."""

from src.pre_process import Inconsistency, ProcessedInstance, Student, TurmaSpec, pre_process
from src.read_instance import RawInstance, RawStudentRow, RawTurmasConfig, read_instance

__all__ = [
    "RawInstance",
    "RawStudentRow",
    "RawTurmasConfig",
    "read_instance",
    "Student",
    "TurmaSpec",
    "Inconsistency",
    "ProcessedInstance",
    "pre_process",
]
