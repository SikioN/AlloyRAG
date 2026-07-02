#!/bin/bash

NAMESPACE=rag
helm uninstall alloyrag-dev --namespace $NAMESPACE
