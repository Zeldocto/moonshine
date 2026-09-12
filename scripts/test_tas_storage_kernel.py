"""Execute project transactions through the real bounded ARM archive worker."""
import ctypes as C
import unittest
import zlib

import test_state_storage_kernel as fixture
from test_state_storage_kernel import Header, EXPORT, IMPORT, WINDOW, CANCEL
from test_state_storage_kernel import OK, IO, BAD, STALE, CANCELLED

BEGIN, READ, COMMIT, CATALOG, RENAME, DELETE = range(8, 14)
NOT_FOUND, BAD_REQUEST = 5, 9


class Context(C.Structure):
    _fields_ = [(name, C.c_uint) for name in
                ('projectId', 'componentId', 'generation', 'role', 'crc', 'r0', 'r1', 'checksum')]


class Component(C.Structure):
    _fields_ = [(name, C.c_uint) for name in
                ('id', 'crc', 'packed', 'frames', 'scene')]


class Tape(C.Structure):
    _fields_ = [(name, C.c_uint) for name in ('id', 'crc', 'packed')]


class TakeData(C.Structure):
    _fields_ = [(name, C.c_uint) for name in
                ('version', 'flags', 'frames', 'position', 'settings', 'startFingerprint',
                 'frameHash', 'transitions', 'transitionHash', 'startScene', 'endScene')] + [
        ('origin', C.c_uint * 2), ('reserved', C.c_uint * 3)]


class Project(C.Structure):
    _fields_ = [(name, C.c_uint) for name in
                ('magic', 'version', 'id', 'generation', 'game', 'build', 'config',
                 'scene', 'current', 'count', 'checksum', 'tapeFrames')] + [
        ('name', C.c_char * 32), ('components', Component * 3), ('tape', Tape), ('start', C.c_uint * 2)]

    def seal(self):
        self.checksum = 0
        self.checksum = zlib.crc32(bytes(self))
        return self


class TasStorageKernelTests(unittest.TestCase):
    setUpClass = classmethod(fixture.StateStorageKernelTests.setUpClass.__func__)
    setUp = fixture.StateStorageKernelTests.setUp
    buffer = fixture.StateStorageKernelTests.buffer
    finish = fixture.StateStorageKernelTests.finish

    def context(self, project=0, component=0, generation=0, role=0, crc=0):
        value = Context(project, component, generation, role, crc)
        if project:
            value.checksum = zlib.crc32(bytes(value)[:28])
        C.memmove(self.lib.mailbox() + 8000, C.byref(value), C.sizeof(value))

    def command(self, command, id=0, crc=0, project=None, name=None):
        self.context()
        if project is not None:
            C.memmove(self.lib.mailbox() + 8032, C.byref(project), C.sizeof(project))
        if name is not None:
            self.lib.requestName(name)
        self.lib.submit(command, id, 0, 0, crc, 11)

    def result_id(self):
        return C.c_uint.from_address(self.lib.mailbox() + 48).value

    def returned(self):
        value = Project.from_buffer_copy(C.string_at(self.lib.mailbox() + 8032, 160))
        self.assertEqual(value.checksum, zlib.crc32(bytes(value)[:40] + bytes(4) + bytes(value)[44:]))
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox() + 88).value, value.checksum)
        return value

    def path(self, project, leaf):
        return f'/Moonshine data/tas/tas_{project:08d}/{leaf}'.encode()

    def file(self, project, leaf):
        size = C.c_uint()
        pointer = self.lib.file(self.path(project, leaf), C.byref(size))
        return C.string_at(pointer, size.value) if pointer else None

    def add(self, project, leaf, data):
        self.assertGreaterEqual(self.lib.add(self.path(project, leaf), self.buffer(bytes(data)), len(data)), 0)

    def begin(self, name=b'Plaza take'):
        self.command(BEGIN, name=name)
        self.assertEqual(self.finish(), OK)
        return self.result_id()

    def export_component(self, id, role, published=None, data=None, scene=0x10203):
        if data is None:
            data = bytes(range(251)) * 171 + bytes([role])
        meta = b'opaque profile and tape sidecar'
        self.lib.prepare(self.buffer(data), len(data), 32, self.buffer(meta), len(meta))
        header = Header.from_address(self.lib.mailbox() + 96)
        header.sceneKey = scene
        header.headerCrc = 0
        header.headerCrc = zlib.crc32(bytes(header))
        self.context(id, 0, published.generation if published else 0, role,
                     published.checksum if published else 0)
        self.lib.submit(EXPORT, 0, 32, len(data), 0, 11)
        self.assertEqual(self.finish(), OK)
        component = self.result_id()
        archive = self.file(id, f'state_{component:08d}.mss')
        h = Header.from_buffer_copy(archive)
        return Component(component, h.headerCrc, h.packedSize, 0 if role == 0 else 12, scene), archive

    def export_tape(self, id, published=None, frames=12, transitions=0):
        take = TakeData(1, 0, frames, frames, 123, 456, 789, transitions, 321, 0x10203, 0x10203)
        take.origin[0] = 12345
        payload = bytes(4) + bytes((i % 251 for i in range(16 * (frames + transitions))))
        self.lib.prepare(self.buffer(payload), len(payload), 32, self.buffer(bytes(take)), 64)
        header = Header.from_address(self.lib.mailbox() + 96)
        header.snapshotVersion = 0x54415001
        header.rawSize = header.packedSize
        header.headerCrc = 0
        header.headerCrc = zlib.crc32(bytes(header))
        C.memmove(self.lib.staging(), payload, len(payload))
        self.context(id, 0, published.generation if published else 0, 3,
                     published.checksum if published else 0)
        self.lib.submit(EXPORT, 0, 0, len(payload), 0, 11)
        self.assertEqual(self.finish(), OK)
        component = self.result_id()
        archive = self.file(id, f'state_{component:08d}.mss')
        h = Header.from_buffer_copy(archive)
        self.assertEqual(archive[160:], payload)
        return Tape(component, h.headerCrc, h.packedSize), archive

    def unpublished(self):
        id = self.begin()
        start, _ = self.export_component(id, 0)
        take, _ = self.export_component(id, 1)
        project = Project(0x4D535450, 2, id, 1, 0x474D534A, 123, 6789, 0x10203, 1, 2)
        project.name = b'Plaza take'
        project.start[0] = 12345
        project.components[0], project.components[1] = start, take
        project.tape, _ = self.export_tape(id)
        project.tapeFrames = 12
        return project.seal()

    def published(self):
        project = self.unpublished()
        self.command(COMMIT, project.id, project=project)
        self.assertEqual(self.finish(), OK)
        return self.returned()

    def read(self, id, crc=0):
        self.command(READ, id, crc)
        self.assertEqual(self.finish(), OK)
        return self.returned()

    def test_publish_reboot_component_import_and_window_keep_pool_intact(self):
        project = self.published()
        self.assertEqual(self.file(project.id, 'project.a'), bytes(project))
        self.assertIsNone(self.file(project.id, 'project.b'))
        self.lib.reboot()
        self.assertEqual(bytes(self.read(project.id)), bytes(project))
        part = project.components[1]
        archive = self.file(project.id, f'state_{part.id:08d}.mss')
        header = Header.from_buffer_copy(archive)
        payload = archive[96 + header.metadataSize:]
        for command in (IMPORT, WINDOW):
            self.context(project.id, part.id, project.generation, 1, project.checksum)
            self.lib.submit(command, part.id, 0, part.packed, part.crc, 11)
            if command == WINDOW:
                self.lib.windowSize(len(payload))
            self.assertEqual(self.finish(), OK)
            self.assertEqual(C.string_at(self.lib.staging(), len(payload)), payload)
        self.command(CATALOG)
        self.assertEqual(self.finish(), OK)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox() + 192).value, 1)
        self.command(3)  # Ordinary savestate catalog remains separate.
        self.assertEqual(self.finish(), OK)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox() + 192).value, 0)

    def test_commit_checks_every_component_payload_and_preserves_old_manifest(self):
        project = self.published()
        replacement, archive = self.export_component(project.id, 1, project)
        corrupt = bytearray(archive)
        corrupt[-1] ^= 0x20
        self.add(project.id, f'state_{replacement.id:08d}.mss', corrupt)
        candidate = Project.from_buffer_copy(bytes(project))
        candidate.generation += 1
        candidate.components[1] = replacement
        candidate.seal()
        pool = C.string_at(self.lib.pool(), self.lib.poolSize())
        self.command(COMMIT, project.id, project.checksum, candidate)
        self.assertEqual(self.finish(), BAD)
        self.assertEqual(C.string_at(self.lib.pool(), self.lib.poolSize()), pool)
        self.assertEqual(bytes(self.read(project.id)), bytes(project))
        self.assertIsNone(self.file(project.id, 'project.b'))

    def test_short_write_sync_rename_and_read_failure_keep_previous_generation(self):
        for fault in ('write', 'sync', 'rename', 'read'):
            with self.subTest(fault=fault):
                self.setUp()
                project = self.published()
                candidate = Project.from_buffer_copy(bytes(project))
                candidate.generation += 1
                candidate.name = b'Changed'
                candidate.seal()
                self.lib.clearIo()
                if fault == 'write': self.lib.failures(20, 0, 0)
                if fault == 'sync': self.lib.failures(0xFFFFFFFF, 1, 0)
                if fault == 'rename': self.lib.failures(0xFFFFFFFF, 0, 1)
                if fault == 'read': self.lib.readFailure(400)
                self.command(COMMIT, project.id, project.checksum, candidate)
                self.assertEqual(self.finish(), IO)
                self.lib.failures(0xFFFFFFFF, 0, 0)
                self.lib.readFailure(0xFFFFFFFF)
                self.assertEqual(bytes(self.read(project.id)), bytes(project))

    def test_stale_generation_wrong_role_or_orphan_cannot_import(self):
        project = self.published()
        orphan, _ = self.export_component(project.id, 2, project)
        for part, generation, role, crc in (
            (project.components[1], project.generation + 1, 1, project.checksum),
            (project.components[1], project.generation, 0, project.checksum),
            (orphan, project.generation, 2, project.checksum),
            (project.components[1], project.generation, 1, project.checksum ^ 1),
        ):
            self.context(project.id, part.id, generation, role, crc)
            self.lib.submit(IMPORT, part.id, 0, part.packed, part.crc, 11)
            self.assertEqual(self.finish(), STALE)

    def test_inactive_generation_is_replaced_and_corrupt_newest_falls_back(self):
        first = self.published()
        self.command(RENAME, first.id, first.checksum, name=b'New name')
        self.assertEqual(self.finish(), OK)
        second = self.returned()
        self.assertEqual(second.generation, 2)
        self.assertEqual(self.file(first.id, 'project.a'), bytes(first))
        self.assertEqual(self.file(first.id, 'project.b'), bytes(second))
        self.lib.reboot()
        self.assertEqual(bytes(self.read(first.id)), bytes(second))
        damaged = bytearray(bytes(second)); damaged[90] ^= 1
        self.add(first.id, 'project.b', damaged)
        self.lib.reboot()
        self.assertEqual(bytes(self.read(first.id)), bytes(first))

    def test_delete_reserves_identity_and_preserves_unrelated_files(self):
        project = self.published()
        self.add(project.id, 'notes.txt', b'User notes')
        self.command(DELETE, project.id, project.checksum)
        self.assertEqual(self.finish(), OK)
        marker = self.file(project.id, 'project.deleted')
        self.assertEqual(len(marker), 32)
        self.assertEqual(int.from_bytes(marker[28:], 'little'), zlib.crc32(marker[:28]))
        self.assertEqual(self.file(project.id, 'notes.txt'), b'User notes')
        self.assertIsNone(self.file(project.id, 'project.a'))
        for part in project.components:
            if part.id:
                self.assertIsNone(self.file(project.id, f'state_{part.id:08d}.mss'))
        self.assertIsNone(self.file(project.id, f'state_{project.tape.id:08d}.mss'))
        self.lib.reboot()
        self.command(READ, project.id)
        self.assertEqual(self.finish(), NOT_FOUND)
        self.assertGreater(self.begin(), project.id)

    def test_failed_tombstone_publish_does_not_delete_project(self):
        project = self.published()
        self.lib.failures(0xFFFFFFFF, 1, 0)
        self.command(DELETE, project.id, project.checksum)
        self.assertEqual(self.finish(), IO)
        self.lib.failures(0xFFFFFFFF, 0, 0)
        self.assertEqual(bytes(self.read(project.id)), bytes(project))
        self.assertIsNone(self.file(project.id, 'project.deleted'))

    def test_catalog_pages_only_published_checked_project_directories(self):
        template = self.published()
        for _ in range(10):
            id = self.begin()
            if id == 5: continue  # An allocated but unpublished project stays hidden.
            value = Project.from_buffer_copy(bytes(template)); value.id = id
            self.add(id, 'project.a', bytes(value.seal()))
        self.command(CATALOG)
        self.assertEqual(self.finish(), OK)
        base = self.lib.mailbox()
        self.assertEqual(C.c_uint.from_address(base + 192).value, 8)
        ids = [C.c_uint.from_address(base + 224 + 64 * i).value for i in range(8)]
        self.assertEqual(ids, [1, 2, 3, 4, 6, 7, 8, 9])
        self.assertEqual(C.c_uint.from_address(base + 204).value, 1)
        self.command(CATALOG, 9)
        self.assertEqual(self.finish(), OK)
        self.assertEqual(C.c_uint.from_address(base + 192).value, 2)

    def test_cancellation_during_verification_does_not_publish(self):
        project = self.published()
        candidate = Project.from_buffer_copy(bytes(project)); candidate.generation += 1; candidate.seal()
        self.command(COMMIT, project.id, project.checksum, candidate)
        self.assertEqual(self.lib.run(5), -1)
        self.command(CANCEL)
        self.assertEqual(self.finish(), CANCELLED)
        self.assertEqual(bytes(self.read(project.id)), bytes(project))

    def test_invalid_context_and_conflicting_generations_fail_closed(self):
        project = self.published()
        self.context(project.id, 1, project.generation, 0, project.checksum)
        C.c_uint.from_address(self.lib.mailbox() + 8028).value ^= 1
        part = project.components[0]
        self.lib.submit(IMPORT, 1, 0, part.packed, part.crc, 11)
        self.assertEqual(self.finish(), BAD_REQUEST)
        conflicting = Project.from_buffer_copy(bytes(project)); conflicting.name = b'Conflict'; conflicting.seal()
        self.add(project.id, 'project.b', bytes(conflicting))
        self.command(READ, project.id)
        self.assertEqual(self.finish(), BAD)

    def test_metadata_damage_missing_component_and_wrong_scene_never_publish(self):
        for fault in ('metadata', 'missing', 'scene'):
            with self.subTest(fault=fault):
                self.setUp()
                project = self.unpublished()
                component = project.components[1]
                leaf = f'state_{component.id:08d}.mss'
                if fault == 'metadata':
                    broken = bytearray(self.file(project.id, leaf)); broken[100] ^= 1
                    self.add(project.id, leaf, broken)
                elif fault == 'missing':
                    component.id = 99
                    project.seal()
                else:
                    project.components[1].scene ^= 1
                    project.seal()
                self.command(COMMIT, project.id, project=project)
                self.assertEqual(self.finish(), NOT_FOUND if fault == 'missing' else BAD)
                self.assertIsNone(self.file(project.id, 'project.a'))
                self.assertIsNone(self.file(project.id, 'project.b'))

    def test_component_context_cannot_overwrite_existing_or_change_while_pending(self):
        project = self.published()
        part = project.components[1]
        original = self.file(project.id, f'state_{part.id:08d}.mss')
        self.context(project.id, part.id, project.generation, 1, project.checksum)
        self.lib.submit(EXPORT, part.id, 32, part.packed, 0, 11)
        self.assertEqual(self.finish(), BAD_REQUEST)
        self.assertEqual(self.file(project.id, f'state_{part.id:08d}.mss'), original)
        self.context(project.id, part.id, project.generation, 1, project.checksum)
        self.lib.submit(IMPORT, part.id, 0, part.packed, part.crc, 11)
        self.assertEqual(self.lib.run(2), -1)
        self.context(project.id, part.id, project.generation, 2, project.checksum)
        self.assertEqual(self.finish(), CANCELLED)
        self.assertEqual(bytes(self.read(project.id)), bytes(project))

    def test_delete_before_publication_and_committed_tombstone_block_resurrection(self):
        project = self.published()
        self.lib.failures(0xFFFFFFFF, 0, 1)
        self.command(DELETE, project.id, project.checksum)
        self.assertEqual(self.finish(), IO)
        self.lib.failures(0xFFFFFFFF, 0, 0)
        self.assertEqual(bytes(self.read(project.id)), bytes(project))
        self.command(DELETE, project.id, project.checksum)
        self.assertEqual(self.finish(), OK)
        # A stale file restored manually cannot resurrect the deleted identity.
        self.add(project.id, 'project.a', bytes(project))
        self.lib.reboot()
        self.command(READ, project.id)
        self.assertEqual(self.finish(), NOT_FOUND)

    def test_successive_commits_preserve_both_manifest_generations_components(self):
        first = self.published()
        replacement, archive = self.export_component(first.id, 1, first)
        second = Project.from_buffer_copy(bytes(first))
        second.generation += 1; second.components[1] = replacement; second.seal()
        self.command(COMMIT, first.id, first.checksum, second)
        self.assertEqual(self.finish(), OK)
        self.assertEqual(bytes(self.returned()), bytes(second))
        self.assertEqual(self.file(first.id, 'project.a'), bytes(first))
        self.assertEqual(self.file(first.id, 'project.b'), bytes(second))
        self.assertIsNotNone(self.file(first.id, f'state_{first.components[1].id:08d}.mss'))
        self.assertEqual(self.file(first.id, f'state_{replacement.id:08d}.mss'), archive)

    def test_successive_saves_reclaim_only_outgoing_unreferenced_components(self):
        current = self.published()
        start_leaf = f'state_{current.components[0].id:08d}.mss'
        start_bytes = self.file(current.id, start_leaf)
        orphan, orphan_bytes = self.export_component(current.id, 2, current)
        orphan_leaf = f'state_{orphan.id:08d}.mss'
        self.add(current.id, 'notes.txt', b'User notes')
        previous = None
        for generation in (2, 3, 4):
            replacement, archive = self.export_component(
                current.id, 1, current, data=bytes([generation]) * 45000)
            candidate = Project.from_buffer_copy(bytes(current))
            candidate.generation = generation
            candidate.components[1] = replacement
            candidate.tape, tape_archive = self.export_tape(current.id, current, frames=generation * 20)
            candidate.tapeFrames = generation * 20
            candidate.seal()
            retired = previous.components[1].id if previous else None
            self.command(COMMIT, current.id, current.checksum, candidate)
            self.assertEqual(self.finish(), OK)
            self.assertEqual(bytes(self.returned()), bytes(candidate))
            if retired is not None:
                self.assertIsNone(self.file(current.id, f'state_{retired:08d}.mss'))
                self.assertIsNone(self.file(current.id, f'state_{previous.tape.id:08d}.mss'))
            self.assertIsNotNone(self.file(current.id, f'state_{current.tape.id:08d}.mss'))
            self.assertEqual(self.file(current.id, f'state_{candidate.tape.id:08d}.mss'), tape_archive)
            self.assertIsNotNone(self.file(current.id, f'state_{current.components[1].id:08d}.mss'))
            self.assertEqual(self.file(current.id, f'state_{replacement.id:08d}.mss'), archive)
            self.assertEqual(self.file(current.id, start_leaf), start_bytes)
            self.assertEqual(self.file(current.id, orphan_leaf), orphan_bytes)
            self.assertEqual(self.file(current.id, 'notes.txt'), b'User notes')
            previous, current = current, candidate
        self.command(RENAME, current.id, current.checksum, name=b'Final take')
        self.assertEqual(self.finish(), OK)
        renamed = self.returned()
        self.assertEqual(renamed.generation, 5)
        self.assertEqual(self.file(current.id, 'project.b'), bytes(current))
        self.assertEqual(self.file(current.id, 'project.a'), bytes(renamed))
        self.assertIsNone(self.file(current.id, f'state_{previous.components[1].id:08d}.mss'))
        self.assertIsNone(self.file(current.id, f'state_{previous.tape.id:08d}.mss'))
        self.assertEqual(self.file(current.id, start_leaf), start_bytes)
        self.assertEqual(self.file(current.id, orphan_leaf), orphan_bytes)
        self.assertEqual(self.file(current.id, 'notes.txt'), b'User notes')
        self.lib.reboot()
        self.assertEqual(bytes(self.read(current.id)), bytes(renamed))

    def test_cleanup_failure_does_not_report_a_published_save_as_failed(self):
        first = self.published()
        second_part, _ = self.export_component(first.id, 1, first)
        second = Project.from_buffer_copy(bytes(first))
        second.generation = 2; second.components[1] = second_part; second.seal()
        self.command(COMMIT, first.id, first.checksum, second)
        self.assertEqual(self.finish(), OK)
        third_part, _ = self.export_component(first.id, 1, second)
        third = Project.from_buffer_copy(bytes(second))
        third.generation = 3; third.components[1] = third_part; third.seal()
        self.command(COMMIT, first.id, second.checksum, third)
        for _ in range(100):
            self.assertEqual(self.lib.run(1), -1)
            if self.file(first.id, 'project.a') == bytes(third):
                break
        else:
            self.fail('New manifest was not published')
        self.lib.unlinkFailure(1)
        self.assertEqual(self.finish(), OK)
        self.assertEqual(bytes(self.returned()), bytes(third))
        self.assertIsNotNone(self.file(first.id, f'state_{first.components[1].id:08d}.mss'))
        self.lib.unlinkFailure(0)
        self.lib.reboot()
        self.assertEqual(bytes(self.read(first.id)), bytes(third))

    def test_zero_frame_project_needs_only_beginning_and_nonempty_tape_envelope(self):
        id = self.begin()
        start, _ = self.export_component(id, 0)
        tape, archive = self.export_tape(id, frames=0)
        project = Project(0x4D535450, 2, id, 1, 0x474D534A, 123, 6789, 0x10203, 0, 1)
        project.name = b'New empty take'; project.start[0] = 12345
        project.components[0] = start; project.tape = tape; project.seal()
        self.assertEqual(archive[160:], bytes(4))
        self.command(COMMIT, id, project=project)
        self.assertEqual(self.finish(), OK)
        self.assertEqual(bytes(self.returned()), bytes(project))

    def test_checkpoint_scenes_are_individual_and_tape_can_import_with_full_pool(self):
        project = self.published()
        replacement, _ = self.export_component(project.id, 2, project, scene=0x34000003)
        tape, archive = self.export_tape(project.id, project, frames=4096, transitions=32)
        candidate = Project.from_buffer_copy(bytes(project)); candidate.generation += 1
        candidate.components[2] = replacement; candidate.count = 3; candidate.current = 2
        candidate.tape = tape; candidate.tapeFrames = 4096; candidate.seal()
        self.command(COMMIT, project.id, project.checksum, candidate)
        self.assertEqual(self.finish(), OK)
        pool = C.string_at(self.lib.pool(), self.lib.poolSize())
        extra = C.string_at(self.lib.extra(), self.lib.expandedSize() - self.lib.poolSize())
        for role, part in ((2, replacement), (3, tape)):
            self.context(project.id, part.id, candidate.generation, role, candidate.checksum)
            self.lib.submit(IMPORT, part.id, 0, part.packed, part.crc, 11)
            self.assertEqual(self.finish(), OK)
        self.assertEqual(C.string_at(self.lib.staging(), tape.packed), archive[160:])
        self.assertEqual(C.string_at(self.lib.pool(), self.lib.poolSize()), pool)
        self.assertEqual(C.string_at(self.lib.extra(), len(extra)), extra)

    def test_valid_outer_checksums_cannot_publish_bad_tape_identity_or_shape(self):
        for fault in ('origin', 'frames', 'flags', 'reserved', 'version', 'length', 'prefix', 'payload_crc'):
            with self.subTest(fault=fault):
                self.setUp(); project = self.published()
                tape, archive = self.export_tape(project.id, project)
                raw = bytearray(archive); h = Header.from_buffer(raw); take = TakeData.from_buffer(raw, 96)
                if fault == 'origin': take.origin[0] += 1
                elif fault == 'frames': take.frames = take.position = 11
                elif fault == 'flags': take.flags = 1
                elif fault == 'reserved': take.reserved[2] = 1
                elif fault == 'version': take.version = 2
                elif fault == 'length': h.rawSize += 4
                elif fault == 'prefix': raw[160] = 1
                elif fault == 'payload_crc': raw[-1] ^= 1
                h.metadataCrc = zlib.crc32(raw[96:160])
                if fault != 'payload_crc': h.payloadCrc = zlib.crc32(raw[160:])
                h.headerCrc = 0; h.headerCrc = zlib.crc32(raw[:96]); tape.crc = h.headerCrc
                self.add(project.id, f'state_{tape.id:08d}.mss', raw)
                candidate = Project.from_buffer_copy(bytes(project)); candidate.generation += 1
                candidate.tape = tape; candidate.seal()
                self.command(COMMIT, project.id, project.checksum, candidate)
                self.assertEqual(self.finish(), BAD)
                self.assertEqual(bytes(self.read(project.id)), bytes(project))

    def test_previous_manifest_version_is_rejected_without_overwriting_it(self):
        project = self.published(); old = Project.from_buffer_copy(bytes(project)); old.version = 1; old.seal()
        self.add(project.id, 'project.a', bytes(old)); self.lib.reboot()
        self.command(READ, project.id)
        self.assertEqual(self.finish(), BAD)
        self.assertEqual(self.file(project.id, 'project.a'), bytes(old))


if __name__ == '__main__':
    unittest.main()
