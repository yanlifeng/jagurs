#!/usr/bin/env python3
"""Maintainer-only: freeze input bytes and reference an existing full trajectory.

This creates no tsunami reference by running the new branch. References are
read from the preserved historical run and retain its source/executable hashes.
"""
from pathlib import Path
import argparse, hashlib, json, shutil, lzma, struct, re, time
import numpy as np
from netCDF4 import Dataset

HERE=Path(__file__).resolve().parent
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,required=True)
    ap.add_argument('--reuse-packed',action='store_true',help='Verify and reuse complete existing packs')
    a=ap.parse_args();old=a.archive.resolve();out=HERE/'data';out.mkdir(exist_ok=True)
    meta=json.loads((old/'case.json').read_text())
    fixed={};files={};start=time.monotonic()
    for name in ['bathy1.grd','bathy2.grd','bathy3.grd','stations.txt']:
        shutil.copyfile(old/name,out/name);fixed[name]=SHA(out/name)
    for grid in range(1,4):
        frames=[Path(v) for v in (old/f'disp{grid}.list').read_text().splitlines() if v.strip()]
        assert len(frames)==182
        # Exact bytewise XOR deltas compress nearly repeated source increments.
        # This encoding introduces no numerical quantization or re-evaluation.
        previous=None;pack=out/f'forcing{grid}.xor.xz'
        reuse=a.reuse_packed and pack.exists()
        with lzma.open(pack,'rb' if reuse else 'wb',preset=None if reuse else 6) as dst:
            if reuse:assert dst.read(11)==b'JAGR-XOR-1\n'
            else:dst.write(b'JAGR-XOR-1\n')
            for k,p in enumerate(frames):
                b=p.read_bytes();v=np.frombuffer(b,dtype=np.uint8)
                if previous is None:previous=np.zeros_like(v)
                assert previous.shape==v.shape
                delta=np.bitwise_xor(v,previous).tobytes()
                if reuse:
                    assert struct.unpack('<Q',dst.read(8))[0]==len(delta)
                    assert dst.read(len(delta))==delta
                else:
                    dst.write(struct.pack('<Q',len(delta)));dst.write(delta)
                previous=v
                name=f'forcing{grid}/frame{k:04d}.grd'
                files[name]=dict(sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
            if reuse:assert dst.read(1)==b''
        print(pack.name,pack.stat().st_size,'bytes',flush=True)
        with pack.open('rb') as src:
            part=0
            while True:
                chunk=src.read(32*1024*1024)
                if not chunk:break
                (out/f'{pack.name}.part{part:03d}').write_bytes(chunk);part+=1
        pack.unlink()
    # Deterministic station selection includes all 11 ocean observation centers
    # plus spatially sorted coastal receivers, independent of their error scores.
    selected=[r['center_west_north_station_ids'][0] for r in json.loads((old/'station_mapping.json').read_text())]
    coast=json.loads((old/'coastal_receiver_mapping.json').read_text())
    available=[r['station_id'] for r in sorted(coast,key=lambda r:(r['latitude_deg'],r['longitude_deg']))]
    for k in np.linspace(0,len(available)-1,37).round().astype(int):
        if available[k] not in selected:selected.append(available[k])
    histories=[];stations=[]
    pattern=re.compile(r't=\s*(\S+)\s+hz=\s*(\S+)\s+fx=\s*(\S+)\s+fy=\s*(\S+)')
    for sid in selected:
        rows=[]
        with (old/f'tgs{sid:06d}').open() as f:
            for line in f:
                m=pattern.search(line)
                if m:
                    row=[float(x.replace('D','E')) for x in m.groups()]
                    if row[0]>1800.10000001:break
                    # 1Hz sampling bounds reference size; fields check all nodes.
                    if abs(row[0]-round(row[0]))<1e-8:rows.append(row)
        hist=np.asarray(rows);assert len(hist)==1800 and hist[-1,0]==1800.
        histories.append(hist);stations.append(sid)
    np.savez_compressed(out/'reference_gauges.npz',station_ids=np.asarray(stations),histories=np.stack(histories))
    fields={}
    for name in ['eta_raw','qx_raw','qy_south_raw','depth_raw']:
        p=old/f'SD03.{name}.00018000.grd'
        with Dataset(p) as d:
            fields[name]=np.asarray(d['z'][:]);fields[name+'_x_range']=np.asarray(d['x_range'][:]);fields[name+'_y_range']=np.asarray(d['y_range'][:])
        fixed[p.name]=SHA(p)
    np.savez_compressed(out/'reference_fields.npz',**fields)
    fixture=HERE.parents[2]/'jagurs-official-baseline-20261013/verification_inputs/standing_wave'
    analytic=out/'analytic';analytic.mkdir(exist_ok=True)
    for p in fixture.iterdir():
        if p.is_file():shutil.copyfile(p,analytic/p.name)
    shutil.copyfile(old/'gridfile.dat',out/'gridfile.dat')
    par=(old/'tsun.par').read_text().replace('tend=10861\n','tend=1800\n').replace('itmap_end=108610\n','itmap_end=18000\n')
    (out/'tsun.par').write_text(par)
    record=dict(format='JAGR-XOR-1',base_tag='JAGURS-D_V0701',base_commit='9934f8970f545deda2cdf4f1bc18f763e191b3cd',
        original_case=old.name,original_executable_sha256=SHA(Path(meta['executable'])),
        duration_s=1800.,native_dt_s=.1,local_dt_s=[.9,.3,.1],source_interval_s=.9,source_frames=182,
        station_count=int((old/'stations.txt').read_text().splitlines()[0]),reference_station_ids=stations,
        grids=[dict(shape=r['shape'],bounds_wesn=r['bounds_wesn'],spacing_arcsec=r['spacing_arcsec']) for r in meta['grids']],
        fixed_input_sha256={k:v for k,v in fixed.items() if not k.startswith('SD03.')},
        reference_raw_grd_sha256={k:v for k,v in fixed.items() if k.startswith('SD03.')},
        source_frames_sha256=files,reference_origin='Directly extracted from the already completed 0..10861s historical trajectory; never generated by the branch under test.',
        physical_source='Published Yamazaki/Cheung/Lay 2018 T-MOD 60-subfault source; prescribed analytical deformation, not CGFDM.',
        source_doi='10.1002/2017JB014749',source_parameters_sha256=meta['source_sha256'],
        terrain_provenance='Original NTHMP2023 Hirota 30/6/1.2 arcsec author terrain on the previously verified 27/9/3 arcsec lattice; northern extension NOAA ETOPO2022. Existing bytes preserved.',
        scope='Rapid numerical regression and representative CPU/MPI kernel workload, not a new historical inundation acceptance.',
        packaging_wall_s=time.monotonic()-start)
    record['distributed_files_sha256']={str(p.relative_to(out)):SHA(p) for p in out.rglob('*') if p.is_file()}
    (HERE/'dataset_manifest.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
    print('Dataset manifest written; selected gauges',len(stations),flush=True)

if __name__=='__main__':main()
