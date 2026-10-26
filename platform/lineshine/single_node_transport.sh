#!/bin/bash
# Source only for the validated single-node CPU route. NOT a multi-node recipe.
export UCX_TLS='^sdma'
export OMPI_MCA_pml=ob1
export OMPI_MCA_btl=self,vader
export OMPI_MCA_coll=tuned,basic,libnbc,self
