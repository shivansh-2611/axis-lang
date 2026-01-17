"""
ELF64 executable generator
macht aus machine code ne richtige linux executable, ohne linker
"""

import struct
from typing import Optional


class ELF64Writer:
    """
    minimaler ELF64 writer für x86-64 linux
    
    layout:
    - ELF header (64 bytes)
    - program header (56 bytes)
    - padding bis page alignment
    - _start stub
    - user code
    
    virtual addr: 0x400000 (standard)
    entry: 0x401000 (_start)
    """
    
    # elf magic numbers und constants
    ELF_MAGIC = b'\x7fELF'
    ELFCLASS64 = 2
    ELFDATA2LSB = 1  # Little Endian
    EV_CURRENT = 1
    ELFOSABI_SYSV = 0
    ET_EXEC = 2  # Executable file
    EM_X86_64 = 0x3E
    
    PT_LOAD = 1
    PF_X = 1  # Execute
    PF_W = 2  # Write
    PF_R = 4  # Read
    
    BASE_VADDR = 0x400000
    PAGE_SIZE = 0x1000
    
    def __init__(self, user_code: bytes, rodata: bytes = b'', string_offsets: dict = None, 
                 bss_size: int = 0, verbose: bool = False):
        """
        Args:
            user_code: Machine Code für main() und andere Funktionen
            rodata: Read-only Data Section (string literals etc)
            string_offsets: Dict von label -> offset in rodata für relocation
            bss_size: Size of BSS section (uninitialized writable data)
            verbose: Debug-Output
        """
        # setup für elf generation
        self.user_code = user_code
        self.rodata = rodata
        self.string_offsets = string_offsets or {}
        self.bss_size = bss_size
        self.verbose = verbose
        
    def log(self, msg: str):
        if self.verbose:
            print(f"[ELF64] {msg}")
    
    def generate_start_stub(self) -> bytes:
        """
        Generates _start Entry Point:
        
        _start:
            xor edi, edi      ; argc = 0 (fake für MVP)
            call main         ; ruft main() auf
            mov edi, eax      ; exit_code = main return value (in eax)
            mov eax, 60       ; syscall number: exit
            syscall           ; exit(code)
        
        Returns:
            Machine Code für _start
        """
        # xor edi, edi
        xor_edi = bytes([0x31, 0xFF])
        
        # call main
        # main lies directly after _start stub
        # _start stub is 16 bytes total:
        #   xor edi, edi (2) + call (5) + mov edi, eax (2) + mov eax, 60 (5) + syscall (2) = 16
        # call rel32 = E8 <offset>
        # offset = (target_addr - (call_end_addr))
        # call is at offset 2, ends at 7
        # main starts at 16, so offset = 16 - 7 = 9
        call_main = bytes([0xE8]) + struct.pack('<i', 9)
        
        # return value von main in edi für exit code
        mov_edi_eax = bytes([0x89, 0xC7])
        
        # exit syscall number
        mov_eax_60 = bytes([0xB8, 0x3C, 0x00, 0x00, 0x00])
        
        syscall = bytes([0x0F, 0x05])
        
        return xor_edi + call_main + mov_edi_eax + mov_eax_60 + syscall
    
    def build_elf_header(self, entry_point: int, program_header_offset: int) -> bytes:
        """
        Builds ELF64 Header (64 bytes).
        
        Args:
            entry_point: Virtuelle Adresse von _start
            program_header_offset: File-Offset zum Program Header Table
        
        Returns:
            64 bytes ELF Header
        """
        # construct elf header byte by byte
        header = bytearray()
        
        # magic number und basic info
        header.extend(self.ELF_MAGIC)
        header.append(self.ELFCLASS64)
        header.append(self.ELFDATA2LSB)
        header.append(self.EV_CURRENT)
        header.append(self.ELFOSABI_SYSV)
        header.extend(bytes(8))
        
        # e_type (2 bytes)
        header.extend(struct.pack('<H', self.ET_EXEC))  # 0x10
        
        # e_machine (2 bytes)
        header.extend(struct.pack('<H', self.EM_X86_64))  # 0x12
        
        # e_version (4 bytes)
        header.extend(struct.pack('<I', self.EV_CURRENT))  # 0x14
        
        # e_entry (8 bytes)
        header.extend(struct.pack('<Q', entry_point))  # 0x18
        
        # e_phoff (8 bytes) - Program Header Table Offset
        header.extend(struct.pack('<Q', program_header_offset))  # 0x20
        
        # e_shoff (8 bytes) - Section Header Table Offset (0 = keine)
        header.extend(struct.pack('<Q', 0))  # 0x28
        
        # e_flags (4 bytes)
        header.extend(struct.pack('<I', 0))  # 0x30
        
        # e_ehsize (2 bytes) - ELF Header Size
        header.extend(struct.pack('<H', 64))  # 0x34
        
        # e_phentsize (2 bytes) - Program Header Entry Size
        header.extend(struct.pack('<H', 56))  # 0x36
        
        # e_phnum (2 bytes) - Number of Program Headers
        # 1 for code+rodata, plus 1 for BSS if needed
        num_phdrs = 2 if self.bss_size > 0 else 1
        header.extend(struct.pack('<H', num_phdrs))  # 0x38
        
        # e_shentsize (2 bytes) - Section Header Entry Size
        header.extend(struct.pack('<H', 0))  # 0x3A
        
        # e_shnum (2 bytes) - Number of Section Headers
        header.extend(struct.pack('<H', 0))  # 0x3C
        
        # e_shstrndx (2 bytes) - Section Header String Table Index
        header.extend(struct.pack('<H', 0))  # 0x3E
        
        assert len(header) == 64, f"ELF Header must be 64 bytes, got {len(header)}"
        return bytes(header)
    
    def build_program_header(self, file_size: int, mem_size: int) -> bytes:
        """
        Builds Program Header für PT_LOAD Segment (56 bytes).
        
        Args:
            file_size: size im File
            mem_size: size im Memory
        
        Returns:
            56 bytes Program Header
        """
        # program header für das loadable segment
        header = bytearray()
        
        # segment type und flags
        header.extend(struct.pack('<I', self.PT_LOAD))
        
        # p_flags (4 bytes) - R+X
        flags = self.PF_R | self.PF_X
        header.extend(struct.pack('<I', flags))  # 0x04
        
        # p_offset (8 bytes) - File Offset
        header.extend(struct.pack('<Q', 0))  # 0x08: Segment startet bei Byte 0
        
        # p_vaddr (8 bytes) - Virtual Address
        header.extend(struct.pack('<Q', self.BASE_VADDR))  # 0x10
        
        # p_paddr (8 bytes) - Physical Address (ignoriert auf x86-64)
        header.extend(struct.pack('<Q', self.BASE_VADDR))  # 0x18
        
        # p_filesz (8 bytes) - Size in File
        header.extend(struct.pack('<Q', file_size))  # 0x20
        
        # p_memsz (8 bytes) - Size in Memory
        header.extend(struct.pack('<Q', mem_size))  # 0x28
        
        # p_align (8 bytes) - Alignment
        header.extend(struct.pack('<Q', self.PAGE_SIZE))  # 0x30
        
        assert len(header) == 56, f"Program Header must be 56 bytes, got {len(header)}"
        return bytes(header)
    
    def build_bss_program_header(self, vaddr: int, mem_size: int) -> bytes:
        """
        Builds Program Header for BSS (writable uninitialized data) Segment (56 bytes).
        
        Args:
            vaddr: Virtual address of BSS segment
            mem_size: Size of BSS in memory
        
        Returns:
            56 bytes Program Header
        """
        header = bytearray()
        
        # segment type
        header.extend(struct.pack('<I', self.PT_LOAD))
        
        # p_flags (4 bytes) - R+W (no execute)
        flags = self.PF_R | self.PF_W
        header.extend(struct.pack('<I', flags))
        
        # p_offset (8 bytes) - File Offset (0 since BSS has no file content)
        header.extend(struct.pack('<Q', 0))
        
        # p_vaddr (8 bytes) - Virtual Address
        header.extend(struct.pack('<Q', vaddr))
        
        # p_paddr (8 bytes) - Physical Address
        header.extend(struct.pack('<Q', vaddr))
        
        # p_filesz (8 bytes) - Size in File (0 for BSS)
        header.extend(struct.pack('<Q', 0))
        
        # p_memsz (8 bytes) - Size in Memory
        header.extend(struct.pack('<Q', mem_size))
        
        # p_align (8 bytes) - Alignment
        header.extend(struct.pack('<Q', self.PAGE_SIZE))
        
        assert len(header) == 56, f"BSS Program Header must be 56 bytes, got {len(header)}"
        return bytes(header)
    
    def generate(self) -> tuple[bytes, int, int]:
        """
        Generates komplettes ELF64 Executable.
        
        Returns:
            tuple(executable Binary, rodata_vaddr, bss_vaddr)
        """
        self.log("Starting ELF64 generation...")
        
        # 1. Generate _start stub
        start_stub = self.generate_start_stub()
        self.log(f"Generated _start stub: {len(start_stub)} bytes")
        
        # 2. Calculate offsets
        elf_header_size = 64
        program_header_size = 56
        num_phdrs = 2 if self.bss_size > 0 else 1
        headers_size = elf_header_size + (program_header_size * num_phdrs)
        
        code_offset = self.PAGE_SIZE  # 0x1000
        padding_size = code_offset - headers_size
        
        # Code + rodata in same segment (simpler, beide read-only)
        total_code_size = len(start_stub) + len(self.user_code)
        rodata_offset = code_offset + total_code_size  # file offset
        rodata_vaddr = self.BASE_VADDR + rodata_offset  # virtual addr
        
        total_file_size = rodata_offset + len(self.rodata)
        
        # BSS virtual address (after rodata, page-aligned)
        bss_vaddr = 0
        if self.bss_size > 0:
            # Put BSS at next page after code+rodata
            bss_page = ((rodata_vaddr + len(self.rodata) + self.PAGE_SIZE - 1) // self.PAGE_SIZE) * self.PAGE_SIZE
            bss_vaddr = bss_page
            self.log(f"BSS vaddr: 0x{bss_vaddr:X} ({self.bss_size} bytes)")
        
        # Entry Point = base + code_offset (wo _start liegt)
        entry_point = self.BASE_VADDR + code_offset
        
        self.log(f"Code offset: 0x{code_offset:X}")
        self.log(f"Entry point: 0x{entry_point:X}")
        self.log(f"Rodata offset: 0x{rodata_offset:X}")
        self.log(f"Rodata vaddr: 0x{rodata_vaddr:X}")
        self.log(f"Total file size: {total_file_size} bytes")
        
        # 3. Build ELF Header
        elf_header = self.build_elf_header(
            entry_point=entry_point,
            program_header_offset=elf_header_size
        )
        
        # 4. Build Program Headers
        program_header = self.build_program_header(
            file_size=total_file_size,
            mem_size=total_file_size
        )
        
        bss_program_header = b''
        if self.bss_size > 0:
            bss_program_header = self.build_bss_program_header(
                vaddr=bss_vaddr,
                mem_size=self.bss_size
            )
        
        # 5. Assemble Binary
        padding = bytes(padding_size)
        executable = elf_header + program_header + bss_program_header + padding + start_stub + self.user_code + self.rodata
        
        self.log(f"Generated ELF64 executable: {len(executable)} bytes")
        
        # Verify size
        assert len(executable) == total_file_size, \
            f"Size mismatch: expected {total_file_size}, got {len(executable)}"
        
        return executable, rodata_vaddr, bss_vaddr

def write_elf_executable(machine_code: bytes, output_path: str, rodata: bytes = b'', 
                          string_offsets: dict = None, bss_size: int = 0, 
                          verbose: bool = False) -> tuple[int, int]:
    """
    Schreibt Machine Code als ELF64 Executable.
    
    Args:
        machine_code: Kompilierter Code (main + andere Funktionen)
        output_path: Pfad zur Output-Datei
        rodata: Read-only data (string literals etc)
        string_offsets: Dict von label -> offset in rodata
        bss_size: Size of BSS section for writable globals
        verbose: Debug-Output
    
    Returns:
        tuple(rodata_vaddr, bss_vaddr): Virtual addresses for relocations
    """
    writer = ELF64Writer(machine_code, rodata=rodata, string_offsets=string_offsets, 
                         bss_size=bss_size, verbose=verbose)
    executable, rodata_vaddr, bss_vaddr = writer.generate()
    
    with open(output_path, 'wb') as f:
        f.write(executable)
    
    # Set executable permission (Unix)
    import os
    import stat
    os.chmod(output_path, os.stat(output_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    
    if verbose:
        print(f"[ELF64] Written executable to: {output_path}")
        print(f"[ELF64] Run with: ./{output_path}")
    
    return rodata_vaddr, bss_vaddr

if __name__ == '__main__':
    # Test: Minimales Programm (ret 0)
    # mov eax, 0; ret
    test_code = bytes([
        0xB8, 0x00, 0x00, 0x00, 0x00,  # mov eax, 0
        0xC3  # ret
    ])
    
    print("=" * 70)
    print("ELF64 Writer - Test")
    print("=" * 70)
    
    writer = ELF64Writer(test_code, verbose=True)
    executable = writer.generate()
    
    output_file = "test_elf64.bin"
    with open(output_file, 'wb') as f:
        f.write(executable)
    
    print(f"\nGenerated: {output_file}")
    print(f"Size: {len(executable)} bytes")
    print("\nELF Header (first 64 bytes):")
    print(' '.join(f'{b:02X}' for b in executable[:64]))
    print("\nProgram Header (bytes 64-120):")
    print(' '.join(f'{b:02X}' for b in executable[64:120]))
    print("\nCode section (at 0x1000):")
    print(' '.join(f'{b:02X}' for b in executable[0x1000:0x1000+32]))
    
    # Set executable
    import os
    import stat
    os.chmod(output_file, os.stat(output_file).st_mode | stat.S_IXUSR)
    
    print(f"\n✓ Executable written to: {output_file}")
    print(f"  (chmod +x applied)")
